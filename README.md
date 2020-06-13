# das_extractor
Extract reactor data from DASGIP® files


## What does it do
das_extractor allows you to export data from bioreactor cultures performed with DASGIP® bioreactors.

### Input
Use directly the zip files generated at the end of the culture. There is no need to unzip them before use!



### Output
Using das_extractor you can extract each file as a single xlsx file or as multiple csv files. Xlsx file will be named as the zip file and each reactor will have its own sheet, while each csv file will have the name of the zip file followed by a suffix containing the reactor number.


### Something more
While doing the conversion, das_extractor renames the columns:
- Columns names are now the same, independently from the reactor number.
- DASGIP® files have different column names between v4 and v5. das_extractor updates all the column names from v4 to v5, so that you can work with only one set of column names. 

## Getting started


### Prerequisites
In order to use das_extractor you will need python with the pandas and numpy libraries.
das_extractor was tested to work with:
```
python == 3.8.2 
pandas == 1.0.3
numpy == 1.18.4
```

### Usage

das_extractor can be used as a library or stand alone.

#### As a library

das_extractor can be imported into a project or a jupyter notebook.

```
import das_extractor
das_extractor.export_all("csv")
```

#### As stand alone

Place das_extractor.py in the same folder with all the DASGIP® zip files which need to be exported. Run it with python from a terminal.

```
(P38) C:\***\das_extractor>python das_extractor.py

INFO:root:12 dasgip zip files have been found. Proceeding to extraction.
INFO:root:exporting DAS01 as xlsx
DEBUG:root:Working on reactor n° 1
DEBUG:root:Working on reactor n° 2
DEBUG:root:Working on reactor n° 3
DEBUG:root:Working on reactor n° 4
DEBUG:root:Finalizing creation of DAS01.xlsx
INFO:root:DAS01 exported successfully as xlsx
```




## License

This project is licensed under the GNU LGPLv3 - see the [LICENSE](LICENSE) file for details





<br><br><br>

### Notice of Non-Affiliation and Disclaimer

This software is not affiliated, associated, authorized, endorsed by, or in any way officially connected with Eppendorf, or any of its subsidiaries or its affiliates. The official Eppendorf website can be found at www.eppendorf.com. The name “DASGIP” as well as related names, marks, emblems and images are registered trademarks of Eppendorf. 
