import sys
import pandas as pd
import numpy as np
from io import StringIO
from zipfile import ZipFile
import warnings
import csv
from typing import Dict, List
import os.path
import glob
import logging


def read_daszip(zip_file: str, internal_file_name_pattern: str = "Control.csv", encoding: str = "ansi") -> str:
    """
    Opens the das zip file. The zip may contain multiple files. Only the one corresponding to the culture is exported.

    Parameters
    ----------
    zip_file : str
        The address of the das zip to open.
    internal_file_name_pattern : str
        Specifies the pattern corresponding to the wanted file in the zip file. The default "Control.csv" should work
        with most of the cases.
    encoding : str
        It is the encoding of the file which is going to be extracted. The default "ansi" has no reason to be changed.

    Returns
    -------
    str
        The text file (composed of csv-like sections) corresponding to the pattern, found inside the zip_file

    Raises
    ------
    RuntimeWarning
        If multiple files, corresponding to the file_name_pattern, are found inside the zip file. It is an hypothetical
        condition: each daszip should correspond to only one culture, and have only one file corresponding to it.
        In any case, the first file is taken.


    """
    with ZipFile(zip_file, "r") as zf:
        zf_list = zf.namelist()
        positives = [file for file in zf_list if internal_file_name_pattern in file]
        if len(positives) > 1:
            warnings.warn("Too many files found in the zip archive. File selected: " + positives[0], RuntimeWarning)

        internal_file = zf.read(positives[0]).decode(encoding)

    return internal_file


def convert_daszip_2_dasdict(internal_file: str) -> Dict[str, pd.DataFrame]:
    """
    Convert each section of dasgip csv-like file to pd.DataFrame and save them in a dict.

    Parameters
    ----------
    internal_file : str
        Raw string extracted by read_daszip. It is the content of the "Control.csv" file inside the das zip

    Returns
    -------
    Dict[str, pd.DataFrame]
        Each section of the csv is converted to a pandas.DataFrame and stored in a dict, with the section name as key.
    """

    overwriting_risk = False
    sections_list = internal_file.split("\r\n\r\n")
    sections_dict = {}

    for section in sections_list:

        section_lines_list = section.lstrip().split("\r\n")
        section_name = section_lines_list[0].strip('["]')

        # to avoid overwriting of sections:
        setup_number = ""
        if overwriting_risk is True:
            section_name = section_name + setup_number

        if section_name[:5] == "Setup" and section_name != "Setups":
            setup_number = section_name[-1]
            if overwriting_risk is True:
                section_name = section_name[:-1]
                warnings.warn(
                    "Specific warning: new section 'Setup#' is being opened before the previous one was closed ("
                    "'Profiles' section, which is the last section of each 'Setup#', not found). This file version "
                    "was not tested for. Errors may arise")
            overwriting_risk = True

        if section_name[:8] == "Profiles":
            # "Profiles" is the last section of each "Setup#"
            overwriting_risk = False

        section_content = section_lines_list[1:]

        try:
            section_df = pd.read_csv(StringIO('\n'.join(section_content)), sep=';')
            if section_name.startswith("TrackData"):
                section_df.columns = h_standardize_das_cdf_cols_names(section_df.columns)
                # Here I could also convert the dates from str to date times
            sections_dict[section_name] = section_df

        except pd.errors.EmptyDataError:
            pass  # If there is no data: no need to create a key for that

        except pd.errors.ParserError:
            sections_dict[section_name] = h_parse_irregular_csv(section_content)

    return sections_dict


def convert_dasdict_2_cdf_dict(dasdict: Dict[str, pd.DataFrame], strict=True) -> Dict[int, pd.DataFrame]:
    """
    Merge the events log to the cdf. The events_df is no longer necessary and each cdf is independent.

    Also: "InoculationTime []" is converted to pd.timedelta. Each row has now a valid inoculation time delta, even if
    negative.

    Parameters
    ----------
    dasdict: Dict[str, pd.DataFrame]
        Dictionary with one cdf for reactor and one events_df, coming from the daszip.
    strict: bool
        If True, each final cdf will have only the events which specifically mention the reactor number in the log. Non
        specific events (common to all reactors) wont be assigned.
        If False, each final cdf will have also the generic events.

    Returns
    -------
    Dict[str, pd.DataFrame]
        Dictionary with a cdf for each reactor. The events log are integrated in the cdf.


    """

    cdf_dict = {x: dasdict[x] for x in dasdict.keys() if x.startswith('TrackData')}
    events_df = h_extract_volume_changes(dasdict["Events"])
    new_cdf_dict = {}

    for reactor_name, reactor_data in cdf_dict.items():
        reactor_num = reactor_name[-1]
        fltr_reactor_events = events_df["Reference"].str.contains("Unit " + reactor_num, na=False)

        if strict is False:
            # Add the events in which no reactor is referenced
            fltr_reactor_events = fltr_reactor_events | events_df["Reference"].isnull()

        cdf_merged = pd.merge_ordered(reactor_data, events_df[fltr_reactor_events], on="Timestamp")

        # Correcting the InoculationTime here.
        cdf_merged["InoculationTime []"] = inoctime(cdf_merged)
        new_cdf_dict[int(reactor_num)] = cdf_merged

    return new_cdf_dict


def h_parse_irregular_csv(irregular_csv: List[str]) -> pd.DataFrame:
    """
    Parse csv with varying number of columns. Specifically made to address missing columns in header.

    Some of the csv-like section of the dasgip file do not have the same number of columns for each row. This causes
    problems, especially when a row has more columns than the header.
    This functions find the maximum number of columns between all the rows and generates new names in the header for
    those columns. The csv is then imported in pandas, by specifying the header just generated.

    Parameters
    ----------
    irregular_csv : list[str]
        list of (str) lines of csv-like file. It is irregular because the header has less columns than at least one row.

    Returns
    -------
    csv_df : pandas.DataFrame
        It is a df in which each row has the same number of columns. Names are generated for the columns which were not
        present in the header

    Raises
    ------
    Warnings
        It may be possible that different dasgip csv files have a different structure. This function was tested on v4
        and v5 of the files and gives no problems. If the structure is different, it may be possible that the output is
        not what it is expected to be.

    """
    reader = csv.reader(irregular_csv, delimiter=';', quotechar='"')
    header = next(reader)
    num_cols = max(len(row) for row in reader)
    names = header + [f'unknown{i + 1}' for i in range(num_cols - len(header))]
    csv_df = pd.read_csv(StringIO('\n'.join(irregular_csv)), names=names, sep=';', skiprows=1)
    return csv_df


def inoctime(cdf: pd.DataFrame, itime=None) -> pd.Series:
    """
    Recreates an "InoculationTime" column. If an inoculation time is manually specified, it uses that one as T0.
    Otherwise it uses the first non null value in the old "InoculationTime" column. The !future!
    result is the inoculation time expressed in hours and decimals of hours
    """

    if itime is None:
        itime_idx = cdf.iloc[:, 2].first_valid_index()
        itime = cdf.iloc[:, 0].iloc[itime_idx]

    inoct = pd.to_datetime(itime)
    timestamp = pd.to_datetime(cdf.iloc[:, 0])
    delta = timestamp - inoct

    return delta


def h_extract_volume_changes(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract the manual volume changes specified in the logs inside "events_df" into specific columns.

    Manual volume additions and removals are explicitly only specified in the "events_df". This function extracts these
    information from the logs (in the "Events" sheet) and distributes them into two new columns: "Vol_added" and
    "Vol_removed".
    A third column, "Liquid_added", is created for later hosting information about the specific liquid added. When a
    solution with a specific concentration will be specified, it will be possible to calculate the changes in the
    concentration in the reactor.

    This function assumes the message format is constant.
    # helper (?) function to convert_dasdict_2_cdf_dict.

    Parameters
    ----------
    events_df: pd.DataFrame
        The df coming from the "Events" sheet in das_dict. Volume changes are expressed as logs.

    Returns
    -------
    pd.DataFrame
        The same df, but now volume changes are expresses as float into specific columns.

    """

    fltr_vol_change = events_df["Description"].str.startswith("Added volume").fillna(False)
    vol_change_float = events_df[fltr_vol_change]["Description"].str[13:-13].astype(float).reindex(
        fltr_vol_change.index)
    new_events_df = events_df.copy()
    new_events_df["Vol_added"] = vol_change_float.where(vol_change_float >= 0)
    new_events_df["Liquid_added"] = np.nan
    new_events_df["Vol_removed"] = vol_change_float.where(vol_change_float < 0).abs()
    # Adding new columns, not related to this function
    new_events_df["Feed_pump"] = None
    new_events_df["Feed_balance"] = None

    return new_events_df


def h_standardize_das_cdf_cols_names(cols_names: pd.Index) -> pd.Index:
    """
    Convert to standard column names: remove reference to reactor number, convert dasgip v4 names to v5.

    After converting the dasgip csv to cdf, each cdf has column names with references to the reactor number. This
    function removes the references so that the column names are the same across each reactor.
    There is also a difference between the names of some of the columns between different versions of the dasgip
    control software. The columns names of the files of version 4 are updated to version 5.
    The highest reactor number supported with this function is 9. Change the regex if higher numbers are needed.

    Examples
    --------
    (V4)    Unit 1.XCO2 1.Out [%]
    (v5)    Unit 1.XCO21.Out [%]
    (CDF)   XCO2.Out [%]

    (V4)    Unit 1.Inoculation Time []
    (v5)    Unit 1.InoculationTime []
    (CDF)   InoculationTime []


    Parameters
    ----------
    cols_names: pd.Index
        Original index.

    Returns
    -------
    pd.Index
        Index, with standardized column names.
    """

    das_converter_dict = {"Inoculation Time []": "InoculationTime []",
                          "pH.Out []": "pH.Out [%]",
                          "CTR [mM/h]": "CTR.PV [mMol/h]",
                          "RQ []": "RQ.PV []",
                          "AU []": "ODAU.PV []",
                          "CX []": "ODCX.PV []",
                          "Level.PV [µS]": "Lvl.PV [µS]",
                          "MA.PV [g]": "BalA.MPV [g]",
                          "MB.PV [g]": "BalB.MPV [g]",
                          "Torque.PV [mNm]": "N.TStirPV [mNm]",
                          "Offline.A []": "OfflineA.OfflineA []",
                          "Offline.B []": "OfflineB.OfflineB []",
                          "Offline.C []": "OfflineC.OfflineC []",
                          "Offline.D []": "OfflineD.OfflineD []",
                          "OTR [mM/h]": "OTR.PV [mMol/h]",
                          "V.PV [mL]": "V.VPV [mL]"}

    cols_names = cols_names.str.replace(r"Unit [0-9]\.", "", regex=True)
    cols_names = cols_names.str.replace(r"\s?[0-9]\.", ".", regex=True)
    cols_names = cols_names.str.replace(r"[0-9]\s\[", " [", regex=True)
    cols_names = pd.Index(cols_names.to_series().replace(das_converter_dict))

    return cols_names


def extract(daszip):
    cdf_dict = convert_dasdict_2_cdf_dict(convert_daszip_2_dasdict(read_daszip(daszip, "Control.csv", "ansi")))
    return cdf_dict



def export_cdf_dict_2_excel(cdf_dict, export_name):
    """ Export the cdf dict to an xlsx file. Each culture has its own sheet."""

    writer = pd.ExcelWriter(f'{export_name}.xlsx')
    for k, cdf in cdf_dict.items():
        logging.debug(f'Working on reactor n° {k}')
        cdf.to_excel(writer, sheet_name=str(k))
    logging.debug(f'Finalizing creation of {export_name}.xlsx')
    writer.save()



def export_cdf_dict_2_csv(cdf_dict, export_name):
    """ Export the cdf dict to csv files. Each culture has its own file."""

    for k, cdf in cdf_dict.items():
        logging.debug(f'Working on reactor n° {k}')
        cdf.to_csv(f'{export_name}-{k}.csv')


def export_all(export_format="xlsx"):

    if export_format not in ["csv", "xlsx"]:
        print(f'Error: "export_format" should be one of: "csv", "xlsx". It was "{export_format}" instead.')
        return

    daszip_list = glob.glob("*.zip")
    logging.info(f'{len(daszip_list)} dasgip zip files have been found. Proceeding to extraction.')

    for daszip in daszip_list:
        das_name = os.path.splitext(daszip)[0]
        cdf_dict = extract(daszip)

        if export_format == "xlsx":
            logging.info(f'exporting {das_name} as xlsx')
            export_cdf_dict_2_excel(cdf_dict, das_name)
            logging.info(f'{das_name} exported successfully as xlsx')

        elif export_format == "csv":
            logging.info(f'exporting {das_name} as csv')
            export_cdf_dict_2_csv(cdf_dict, das_name)
            logging.info(f'{das_name} exported successfully as csv')


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    export_all()

