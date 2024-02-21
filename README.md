# clingen-ai-tools
Tools for preparing ClinGen, ClinVar and GenCC datasets for use in machine learning and Large Language Model analysis.

## Features
* Pre-configured for multiple data source files from ClinGen, ClinVar and GenCC.
* Automatic download of source files when files are available on public servers.
* Filtering output by gene or variant id.
* Filtering output to include specified columns.
* Output encoding for one-hot, categorical, and mapping values to ranks or new values
* Future: date handling
* Included mappings for subset of columns
* Expands value-list columns to multiple rows
* Extendable to new data sources through configuration
* Generates new configuration files for new sources, including value counts

## Prerequisites

Python 3 is required (tested with Python 3.9.18), as well as the following modules.
```
 python -m pip install pandas argparse sklearn.preprocessing pyyaml requests
```

## Usage

To use `clingen-ai-tools`, run the `main.py` script in the root project directory. 

Command line options include:

| Option            | Description                                                                                                            |
|-------------------|------------------------------------------------------------------------------------------------------------------------|
| --debug           | Provide detailed debugging information.                                                                                |
| --info            | Provide high level progress information.                                                                               |
| --onehot          | Generate output for columns configured to support one-hot encoding.                                                    |
| --categories      | Generate output for columns configured to support categorical encoding.                                                |
| --expand          | For columns configured to expand, generate a row for each value if more than one value for a row.                      | 
| --map             | For values configured to map, generate new columns with values mapped based on the configuration mapping.csv.          |
| --download        | Download source files when not present. Download source files when not present. Configured with config.yml.            |
| --force           | Download source files even if already present.                                                                         |
| --counts          | Generate value counts for the source files (helpful for determining mapping candidates).                               |
| --generate-config | Generate configuration files (config.yml, dictionary.csv, mapping.csv). May take multiple steps if no files yet exist. |
| --sources         | List of sources to process, default is all sources.                                                                    |
| --columns         | Column names to output. May specify comma separated list. Default is all columns.                                      |
| --output          | Name of the overall output file. Default is `output.csv`.                                                              |
| --individual      | Generate individual output files, one per source, that include the encodings and mappings.                             |
| --join            | Create a joined data file using left joins following the --sources list. --sources must be specified.                  |
| --variant         | Filter output by clinvar variation-id(s). May specify comma separated list. Default include all records.               | 
| --gene            | Filter output by gene symbol(s). May specify comma separated list. Default is all records.                             |

## Example Usage

Force downloads of all sources.
```
python main.py --download --force --info
```
Generate mappings, categorical and onehot encodings, filter by gene MYH7 and left join the sources vrs, 
clinvar-variant-summary, gencc-submissions, and clingen-overall-scores-adult.
``` 
python main.py --info --map --categories --expand --onehot --gene="MYH7" --join --sources="vrs,clinvar-variant-summary,gencc-submissions,clingen-overall-scores-adult"
```

Generate an individual output file for vrs and clingen-overal-scores-pediatric, while expanding references to multiple genes,
and producing onehot and categorical encodings.
```
python main.py --debug --expand --onehot -cateogries --individual --sources="clingen-overall-scores-pediatric,vrs"
```

## Source Configuration
The program looks for sources in the ./sources subdirectory. By convention, the "name" of a source is the name of its 
subdirectory. Each source subdirectory has from 2 to 3 configuration files: `config.yml`, `dictionary.csv`, and 
optionally `mapping.csv`. These contain metadata for the file, fields, and field values of the source, and control
how the source is downloaded and transformed by the program.

### config.yml
A valid source is one that has a `config.yml` file in its directory.
A `config.yml` file contains meta-data about the source such as the url for downloading, optional md5 checksum
file, file format (csv or tab-delimited), quoting strategy, header row location, whether to unzip the downloaded file,
and whether to strip extraneous # characters from the header.

This example shows the `config.yml` for the ClinVar Variant Summary source. The `name` matches the source subdirectory
name. The `url` is used to download the data file to the `download_file` (if specified) or `file` (if download_file is 
not specified). The downloaded file is then uncompressed as directed by the `gzip` flag to `file`.

The file header is the first (0) row following the list of rows to skip `skip_rows`. The format of the file is
tab-delimited (`tab`).

```
--- # ClinVar Submission Summary
- name: clinvar-submission-summary
  url: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/submission_summary.txt.gz
  download_file: submission_summary.txt.gz
  gzip: 1
  file: submission_summary.txt
  header_row: 0
  skip_rows: 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16
  delimiter: tab
  quoting: 3
  strip_hash: 1
  md5_url: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/submission_summary.txt.gz.md5
  md5_file: submission_summary.txt.gz.md5
```
| Setting       | Description                                                                                                                                |
|---------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| name          | Unique name for the source that should match the subdirectory name.                                                                        |
| url           | A web url suitable for downloading the data file.                                                                                          |
| download_file | Optional. When downloading a compressed file, download_file is the name of the compressed file.                                            |
| gzip          | 0 or 1, to indicate whether to decompress the downloaded file.                                                                             |
| file          | The name of the downloaded file (if uncompressed) or the name of the file after decompressing.                                             |
| header_row    | The row number, staring at 0 for the first row, containing the column headers. Count beings following any skipped rows.                    |
| skip_rows     | A comma separated list of rows to skip (0 first row). Useful for when there are extra header rows with meta data in the source file.       |
| delimiter     | `tab` or `comma`, to inform about file structure (csv or tsv).                                                                             |
| quoting       | Default 0. Pandas quoting strategy to use when reading the file: {0 = QUOTE_MINIMAL, 1 = QUOTE_ALL, 2 = QUOTE_NONNUMERIC, 3 = QUOTE_NONE}. |
| strip_hash    | 0 or 1, to indicate whether to strip leading and trailing hash (#) characters from column headers. |
| md5_url       | Optional. A web url suitable for downloading an md5 checksum file. |
| md5_file      | Optional. The name of the downloaded md5 checksum file. |

### dictionary.csv
Each source should also have a `dictionary.csv` file which provides meta-data about the columns in the source file.
It includes a row for each column which contains the field name, definition, joinability group, and flags to enable
one-hot encoding, categorical encoding, mapping, row expansion, etc.

The below shows a sample dictionary for the clingen-dosage source. "GENE SYMBOL" and "HGNC ID" are configured to
support the join-group's "gene-symbol" and "hgnc-id", allowing those columns to be used to join with other source files
containing either of those join-groups. The "HAPLOINSUFFICIENCY" and "TRIPLOSENSITIVITY" are configured for both
categorical encoding (string values to numbers) and to mapping encoding which will utilize the mapping.csv to generate
additional columns for the output based on each value.

```
"column","comment",join-group,onehot,category,continuous,text,map,days,age,expand
GENE SYMBOL,"Official gene symbol of the assertion.",gene-symbol,FALSE,FALSE,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE
"HGNC ID","HGNC id for the specified gene in the form `HGNC:<hgnc gene id>`",hgnc-id,FALSE,FALSE,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE
"HAPLOINSUFFICIENCY","Interpretation category for haploinsufficiency and inheritance mode if applicable, for example 'Gene Associated with Autosomal Recessive Phenotype' or 'Little Evidence for Haploinsufficiency'.",,FALSE,TRUE,FALSE,TRUE,TRUE,FALSE,FALSE,FALSE
"TRIPLOSENSITIVITY","Interpretation category for triploinsufficiency and inheritance mode if applicable, for example 'Sufficient Evidence for Triplosensitivity', 'Dosage Sensitivity Unlikely' or 'Little Evidence for Triploinsufficiency'.",,FALSE,TRUE,FALSE,TRUE,TRUE,FALSE,FALSE,FALSE
"ONLINE REPORT","A URL to the dosage sensitivity report at clinicalgenome.org.",,FALSE,FALSE,FALSE,TRUE,FALSE,FALSE,FALSE,FALSE
"DATE","Date added or last updated.",,FALSE,FALSE,FALSE,TRUE,FALSE,TRUE,TRUE,FALSE
```

The `dictionary.csv` contains the following columns:
| Column | Description |
|--------|-------------|
| column | The exact column header name from the file, stripped of hashes if configured to do so. |
| comment | A brief description of the column. |
| join-group | A token alias string used to designate columns across different sources that contain the same information values, such as a gene symbol. Required for supporing joining across files with --join. |
| onehot | With --onehot, generate new output columns for each value of the column, with values of 0 or 1 depending on if the row has the specific value. |
| category | With --categories, generate a new column with values mapped to unique numbers. |
| continuous | Placeholder for future feature. Currently not implemented or supported. |
| text | Placeholder for future feature. Currently not implemented or supported. |
| map | With --map, use `mapping.csv` to create new output columns based on values in the column. |
| days | Not yet implemented. With --days, generate a new output column with the number of days since Jan 1 1970 to the date value. |
| age | Not yet implemented. With --age, genarate a new output column with the number of days between today and the date value. |
| expand | With --expand, if a column has a list of values (comma-separated) in a row, generate one output row per value, creating a new column for the single value. |

### mapping.csv
Each source may optionally have `mapping.csv` file. If the `map` column is set to true in the dictionary for a specific
field, then the mapping file will be used to map values in the specified column to new values as specified in the map
file. Multiple mapping sets can exist for a field and each will generate a new output column in which values for the
original field are mapped to new values via a simple lookup strategy. The new output column will be named according
to the `map-name` column in the map.

The `mapping.csv` file for the `clingen-dosage` source is as follows. The `column` matches the dictionary and header
column name, the `value` contains the specific values that the column may contain, the `map-name` is the name of the
new output column to create for the mapping, and `map-value` is the new value to set in the new output column based
on the orginal column value.

```
column,value,frequency,map-name,map-value
HAPLOINSUFFICIENCY,Gene Associated with Autosomal Recessive Phenotype,736,haplo-insuff-rank,-0.01
HAPLOINSUFFICIENCY,Sufficient Evidence for Haploinsufficiency,365,haplo-insuff-rank,0.99
HAPLOINSUFFICIENCY,No Evidence for Haploinsufficiency,262,haplo-insuff-rank,0.5
HAPLOINSUFFICIENCY,Little Evidence for Haploinsufficiency,117,haplo-insuff-rank,0.75
HAPLOINSUFFICIENCY,Dosage Sensitivity Unlikely,35,haplo-insuff-rank,0.01
HAPLOINSUFFICIENCY,Emerging Evidence for Haploinsufficiency,26,haplo-insuff-rank,0.9
TRIPLOSENSITIVITY,No Evidence for Triplosensitivity,1248,triplo-insuff-rank,0.5
TRIPLOSENSITIVITY,Little Evidence for Triplosensitivity,11,triplo-insuff-rank,0.75
TRIPLOSENSITIVITY,Emerging Evidence for Triplosensitivity,3,triplo-insuff-rank,0.9
TRIPLOSENSITIVITY,Dosage Sensitivity Unlikely,3,triplo-insuff-rank,0.01
TRIPLOSENSITIVITY,Sufficient Evidence for Triplosensitivity,2,triplo-insuff-rank,0.99
TRIPLOSENSITIVITY,Gene Associated with Autosomal Recessive Phenotype,1,triplo-insuff-rank,-0.01
```

A `mapping.csv` file contains the following columns:

| Column | Description                                                                                                              |
| ------ |--------------------------------------------------------------------------------------------------------------------------|
| column | The name of the column in the source file, which matches the header name and the dictionary entry.                       |
| value | The distinct values of the original column in the source file (will be mapped to a new value).                           |
| frequency | Optional. Created during configuration auto-generation to give context to the frequency of the value in the source file. |
| map-name | The name of the new column to be created for the mapping in the output file.                                             |
| map-value | The new value to be mapped to based on the existing column value.                                                        |

## Adding a New Source

To add a new source data file, first create a new subdirectory in the ./sources directory. Ideally no spaces in the 
directory name. Then run the program using --generate-config.

```commandline
cd ./sources
mkdir new-source-file-name
cd ..
python main.py --generate-config
```
This will create a `config.yml` in the ./new-source-file-name directory which will need to be edited.

```
--- # Source file description
- name: source-name # usually directory name
  url: # put download url here (e.g. https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz)
  download_file: # put name of download file here if different from final file name (e.g. for gz first) (optional)
  file: data.tsv # put name of download file here (if gzip then put the final unzipped name here)
  gzip: 0 # 0 = no gzip, 1 = use gunzip to transform download_file to file
  header_row: 0 # the row number in file that contains the column headers starting at row zero for first line
  skip_rows: None # comma separated list of rows to skip starting at 0 before the header (header 0 after skipped rows)
  delimiter: tab # tab or csv delimited?
  quoting: 0 # Pandas read_csv quoting strategy {0 = QUOTE_MINIMAL, 1 = QUOTE_ALL, 2 = QUOTE_NONNUMERIC, 3 = QUOTE_NONE}
  strip_hash: 1 # Whether to strip leading hash(#) from column names (1=strip, 0=don't)
  md5_url: # Download url for md5 checksum file (optional)
  md5_file: # Name of md5 checksum file to download (optional)
```

Now set each of the values in the new `config.yml` to meet the requirements. Usually, you will need a `name`,
`url`, `file`, and `delimiter` choice at a minimum.

Once you've made the edits, run the program again with the --download option and the --sources option.

```
python main.py --download --sources="new-source-file-name"
```

If the file has been successfully downloaded, you can now run the --generate-config again to create template files 
for `dictionary.csv`.

```
python main.py --generate-config --sources="new-source-file-name"
```

Edit the new `dictionary.csv` and set the flags and configurations for each column. Most flags default to False.
If you configure any columns for mapping, then if you run --generate-config again, it will generate a mapping file
template for those columns with the known values in the file with the frequency data of each value (--counts).

```
python main.py --generate-config --counts --sources="new-source-file-name"
```

Edit the `mapping.csv` file to create the specific output values and mapping sets you desire.