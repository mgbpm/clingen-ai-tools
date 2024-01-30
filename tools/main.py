import pandas as pd
import argparse
from sklearn.preprocessing import LabelEncoder
import os
import yaml
from os import access, R_OK
from os.path import isfile
import requests
import hashlib


# TODO:
#  ** investigate python template libraries for LLM text generation
#  ** add option to create txt output file based on a single AlleleID or
#       VariationID across files in a structured format appropriate for LLM

# TODO:
#  ** add a configuration for allowing n/a value choice, but also have a default

# TODO:
#  ** allow gzip option for downloads
# import gzip
# import shutil
# with gzip.open('file.txt.gz', 'rb') as f_in:
#     with open('file.txt', 'wb') as f_out:
#         shutil.copyfileobj(f_in, f_out)

# TODO:
#  ** allow md5 checksum comparison for downloaded file
#  compare md5 checksum of file or download_file to value contained in md5 checksum file
# import hashlib

def get_md5(filename_with_path):
    file_hash = hashlib.md5()
    with open(filename_with_path, "rb") as f:
        while chunk := f.read(8192):
            file_hash.update(chunk)
        if args.debug:
            print(file_hash.digest())
            print(file_hash.hexdigest())  # to get a printable str instead of bytes
    return file_hash.hexdigest()

# constants
one_hot_prefix = 'hot'
categories_prefix = 'cat'
ordinal_prefix = 'ord'
rank_prefix = 'rnk'
sources_path = '../sources'

pd.set_option('display.max_rows', 1000)
pd.set_option('display.max_columns', 1000)


#########################
#
# PROGRAM ARGUMENTS
#
#########################

parser = argparse.ArgumentParser(
                    prog='clingen-dosage-ai-tools',
                    description='Prepares ClinVar, ClinGen, and GenCC sources for use by ML and LLM analysis.',
                    add_help=True,
                    allow_abbrev=True,
                    exit_on_error=True)
# debug/info
parser.add_argument('-d', '--debug', action='store_true', default=False, help="Provide additional debugging and other information.")
parser.add_argument('-i', '--info', action='store_true',  default=False, help="Provide progress and other information.")

# encoding options
parser.add_argument('--scaling', action='store_true', help="Min/max scaling for variables to 0 to 1 range.")
parser.add_argument('--onehot', action='store_true', help="Generate one-hot encodings for columns that support it.")
parser.add_argument('--categories', action='store_true', help="Generate category encodings for columns that support it.")
parser.add_argument('--continuous', action='store_true', help="Generate continuous variables for columns that support it.")
parser.add_argument('--group', action='store_true', help="Generate new columns based on mapping group configuration.")
parser.add_argument('--rank', action='store_true', help="Generate new columns based on mapping rank configuration.")

# configuration management
parser.add_argument('--download', action='store_true', help="Download datafiles that are not present. No processing or output with this option.")
parser.add_argument('--force', action='store_true', help="Download datafiles even if present and overwrite (with --download).")
parser.add_argument('--counts', action='store_true', help="Generate unique value counts for columns configured for mapping and ranking.")
parser.add_argument('--generate-config', action='store_true', dest='generate_config', help="Generate templates for config.yml, dictionary.csv, and mapping.csv (--counts will also include value frequencies).")

# output control
parser.add_argument('-s', '--sources', help="Comma-delimited list of sources to include based on 'name' in each 'config.yml'.",
    type=lambda s: [item for item in s.split(',')]) # validate below against configured sources
parser.add_argument('-c', '--columns', help="Comma-delimited list of columns to include based on 'column' in *.dict files.",
    type=lambda s: [item for item in s.split(',')]) # validate below against configured dictionaries
parser.add_argument( '-o', '--output',  action='store', type=str, default='output.csv', help = 'The desired output file name.' )
parser.add_argument( '-v', '--variant',  action='store', type=str, help = 'Filter to a specific variant/allele.' )
parser.add_argument( '-g', '--gene',  action='store', type=str, help = 'Filter to a specific gene (symbol).' )


args = parser.parse_args()

# source selection
        # --sources="name1,name2,name3,..."
    # column selection
        # --columns="column1,column2,column3..."
    # filters
        # --filter="column=value"
    # debug options
        # --debug
        # --info
        # --check; validate input options, validate files exist, validate dictionaries complete


###############################
#
# GENERATE CONFIGURATION YML
#
###############################
config_yml = """--- # Source file description
- name: source-name # usually directory name
  url: # put download url here (e.g. https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz)
  download_file: # put name of download file here if different from final file name (e.g. if you download gz first) (optional)
  file: data.tsv # put name of download file here (if gzip then put the final unzipped name here)
  gzip: 0 # 0 = no gzip, 1 = use gunzip to transform download_file to file
  header_row: 0 # the row number in file that contains the column headers starting at row zero for first line
  skip_rows: 0 # how many rows to skip after header for first data line
  delimiter: tab # tab or csv delimited?
  quoting: 0 # Pandas read_csv quoting strategy for the file {0 = QUOTE_MINIMAL, 1 = QUOTE_ALL, 2 = QUOTE_NONNUMERIC, 3 = QUOTE_NONE}
  strip_hash: 1 # Whether to strip leading hash(#) from column names (1=strip, 0=don't)
  md5_url: # Download url for md5 checksum file (optional)
  md5_file: # Name of md5 checksum file to download (optional)
"""
if args.generate_config:
    cnt = 0
    for root, dirs, files in os.walk(sources_path):
        for d in dirs:
            yml = '{}/{}/{}'.format(sources_path, d, 'config.yml')
            if isfile(yml) and access(yml, R_OK):
                if args.debug:
                    print("Found existing config.yml", yml)
            else:
                cnt += 1
                if args.info:
                    print("Need to create", yml)
                with open(yml, 'w') as file:
                    file.write(config_yml)
    if cnt == 0:
        print("All data sources have a config.yml")
    else:
        print("Created",cnt,"config.yml files.")

#########################
#
# LOAD SOURCE CONFIGURATION
#
#########################

# find and create a list of all the config.yml files
configList = []
for root, dirs, files in os.walk(sources_path):
    for f in files:
        if f == 'config.yml':
            file = '{}/{}/{}'.format(sources_path, os.path.basename(root), f)
            configList += [file]
            if args.debug:
                print(file)

if args.debug:
    print("config file list:")
    print(configList)

# load all the config files into a source list dataframe
sourcefiles = pd.DataFrame(columns=['name','path','url','download_file','file','gzip','header_row',
                                    'skip_rows','delimiter','quoting','strip_hash','md5_url','md5_file'])
for c in configList:
    path = c.replace('/config.yml', '') # path is everything but trailing /config.yml
    with open(c, "r") as stream:
        try:
            config = yaml.safe_load(stream)[0]
            if args.debug:
                print("config:", c)
                print(config)
                print()
            # add to config dataframe
            sourcefiles.loc[len(sourcefiles)] = [
                config.get('name'), path, config.get('url'), config.get('download_file'),
                config.get('file'), config.get('gzip'), config.get('header_row'),
                config.get('skip_rows'), config.get('delimiter'), config.get('quoting'),
                config.get('strip_hash'), config.get('md5_url'), config.get('md5_file')
            ]

        except yaml.YAMLError as exc:
            print(exc)
            exit(-1)

# annotate source list with helper columns
sourcefiles['dictionary'] = sourcefiles.apply(lambda x: 'dictionary.csv', axis=1)
sourcefiles['mapping'] = sourcefiles.apply(lambda x: 'mapping.csv', axis=1)

if args.debug:
    print(sourcefiles)


#########################
#
# SOURCE LIST FILTRATION
#
#########################

# validate sourcefile selections in arguments if any
if args.sources == None:
    sources = sourcefiles['name']
else:
    sources = list(set(sourcefiles['name']) & set(args.sources))

# any invalid sources?
invsources = set(sources).difference(sourcefiles['name'])
if len(invsources) > 0:
    print("Invalid source file specficied in --sources parameter: ", invsources)
    exit(-1)

if args.debug:
    print("Using source files: ", sources)

# restrict source list configuration by names
if args.sources:
    sourcefiles = sourcefiles.loc[sourcefiles['name'].isin(sources)]

if args.debug:
    print("Source configurations: ", sourcefiles)


#########################
#
# DOWNLOAD DATA FILES
#
#########################

# if url, get file
#   if download_file, move downloaded file to download_file (if not the same)
#   if file, move downloaded file to file (if not the same)
# if md5 url,
#   get md5 file
#   generate md5 of data file
#   compare to checksum file (error/exit if no match)
# if gzip
#   unzip download_file to file

# TODO: refactor to put if-download within the loop and instead verify all the datafiles?

for i, s in sourcefiles.iterrows():
    source_path = s.get('path')
    download_file = ''
    download_file_path = ''
    if s.get('download_file'):
        download_file = s.get('download_file')
        download_file_path = source_path + '/' + download_file
        if args.debug:
            print("download_file specified for ", s.get('name'), "as", download_file)
    md5_file = ''
    md5_file_path = ''
    if s.get('md5_file'):
        md5_file = s.get('md5_file')
        md5_file_path = source_path + '/' + md5_file
    datafile = ''
    datafile_path = ''
    if s.get('file'):
        datafile = s.get('file')
        datafile_path = source_path + '/' + datafile
        if args.debug:
            print("datafile specified for ", s.get('name'), "as", datafile_path)
    # see if the file is present
    need_download = False
    if len(datafile_path) > 0:
        if args.force:
            need_download = True
        else:
            if isfile(datafile_path) and access(datafile_path, R_OK):
                if args.debug:
                    print("Found existing readable file", datafile_path)
            else:
                if args.download:
                    need_download = True
                else:
                    print("ERROR: missing source file",datafile_path,"; specify --download to acquire.")
                    exit(-1)
    else:
        print("No datafile specified for",s.get('name'),"!")
        exit(-1)
    if need_download:
        if args.download:
            # need md5 file?
            # download md5
            url = s.get('url')
            if url:
                if len(download_file) > 0:
                    print("Downoading", s.get('url'), "as", download_file_path)
                    #filename = wget.download(s.get('url'), out=source_path)
                    r = requests.get(s.get('url'))
                    open(download_file_path, 'wb').write(r.content)
                    print("Completed download of", download_file_path)
                else:
                    print("Downoading", s.get('url'), "as", datafile_path)
                    #filename = wget.download(s.get('url'), out=source_path)
                    r = requests.get(s.get('url'))
                    open(datafile_path, 'wb').write(r.content)
                    print("Completed download of", datafile_path)
            else:
                print("WARNING: no url for", datafile, "for", s.get('name'))
            print("Complete")
    else:
        print("Data file", datafile, "already present.")


#########################
#
# FIELD CONFIG DICTIONARY
#
#########################

def generate_dictionary(sourcefile):
    # open data file
    # create dataframe with appropriate columns
    # create one row per column header
    # save dataframe as csv

#  verify existence of source dictionaries
missing_dictionary = 0
for index, sourcefile in sourcefiles.iterrows():
    dictionary_file = sourcefile['path'] + '/' + sourcefile['dictionary']
    if isfile(dictionary_file) and access(dictionary_file, R_OK):
        if args.debug:
            print("Found dictionary file",dictionary_file)
    else:
        print("WARNING: Missing dictionary file",dictionary_file)
        missing_dictionary += 1
        if args.generate_config:
            generate_dictionary(sourcefile)

if missing_dictionary:
    if not args.generate_config:
        print(missing_dictionary,"missing dictionaries. Use --generate-config to create template configurations.")
        exit(-1)
else:
    if args.debug:
        print("Verified all dictionaries exist.")

# setup sources dictionary
dictionary = pd.DataFrame(columns=['path', 'file', 'column', 'comment', 'onehot', 'category', 'continuous',
                                   'text', 'group', 'rank', 'days', 'age'])
data = dict()
global sourcecolumns, map_config_df

#  process each source file and dictionary
for index, sourcefile in sourcefiles.iterrows():

    if args.debug:
        print(sourcefile['path'], sourcefile['file'], sourcefile['dictionary'], "sep='" + sourcefile['delimiter'] + "'")

    delimiter = sourcefile['delimiter']
    if delimiter == 'tab':
        separator = '\t'
    elif delimiter == 'comma':
        separator = ','
    else:
        separator = None

    # read source dictionary
    if args.debug:
        print("Reading dictionary")

    if args.debug:
        print("sourcefile =", sourcefile)
    dictionary_file = sourcefile['path'] + '/' + sourcefile['dictionary']

    if args.info:
        print("Read dictionary", dictionary_file)
    dic = pd.read_csv(dictionary_file)

    if args.debug:
        print(dic)

    # add dictionary entries to global dic if specified on command line, or all if no columns specified on command line
    for i, r in dic.iterrows():
        if args.columns == None or r['column'] in args.columns:
            dictionary.loc[len(dictionary)] = [sourcefile['path'], sourcefile['file'], r['column'], r['comment'], r['onehot'], r['category'], r['continuous'], r['text'], r['group'], r['rank'], r['days'], r['age']]

    if args.debug:
        print("Dictionary processed")

    # read source sources
    if args.info:
        print("Reading source sources",sourcefile['name'],"...")

    sourcefile_file = sourcefile['path'] + '/' + sourcefile['file']
    if args.columns == None:
        data.update({sourcefile['name']: pd.read_csv(sourcefile_file,
                                                     header=sourcefile['header_row'], sep=separator,
                                                     skiprows=sourcefile['skip_rows'], engine='python',
                                                     quoting=sourcefile['quoting'],
#                                                     nrows=100,
                                                     on_bad_lines='warn')})
        sourcecolumns = list(set(dic['column']))
    else:
        sourcecolumns = list(set(dic['column']) & set(args.columns))
        data.update({sourcefile['name']: pd.read_csv(sourcefile_file,
                                                     # usecols=sourcecolumns,
                                                     usecols=lambda x: x.strip(' #') in sourcecolumns,
                                                     header=sourcefile['header_row'], sep=separator,
                                                     skiprows=sourcefile['skip_rows'], engine='python',
                                                     quoting=sourcefile['quoting'],
#                                                     nrows=100,
                                                     on_bad_lines='warn')})
    if sourcefile['strip_hash'] == 1:
        print("Strip hashes and spaces from column labels")
        df = data[sourcefile['name']]
        #rename columns
        for column in df:
            newcol = column.strip(' #')
            if newcol != column:
                print("Stripping",column,"to",newcol)
                data[sourcefile['name']] = df.rename({column: newcol}, axis='columns')
            else:
                print("Not stripping colum", column)
        print(data[sourcefile['name']])
    else:
        print("Not stripping column labels")

    # show count of unique values per column
    if args.debug or args.counts:
        print(sourcefile['name'],":",
            data[sourcefile['name']].nunique()
            )
        print("Finshed reading source file")
        print()
        print()

    # read mapping file, if any, and filter by selected columns, if any
    mapping_file = sourcefile['path'] + '/' + 'mapping.csv'
    map_config_df = pd.DataFrame()
    if not args.generate_config:
        map_config_df = pd.read_csv(mapping_file)
        map_config_df = map_config_df.loc[map_config_df['column'].isin(sourcecolumns)]

        if args.info:
            print("Mapping Config:",map_config_df)

    # for rank and group columns, show the counts of each value
    if args.counts:
        # loop through each column that has rank and/or group set to True
        # sourcecolumns has list of columns to sift through for settings
        if args.generate_config:
            # create map configs dataframe to collect the values
            map_config_df = pd.DataFrame(
                columns=['column','value','frequency','group','rank']
            )
        df = data[sourcefile['name']]
        for i, r in dic.iterrows():
            if r['group'] == True or r['rank'] == True:
                print()
                print("unique values and counts for",sourcefile['path'],sourcefile['file'],r['column'])
                value_counts_df = df[r['column']].value_counts().rename_axis('value').reset_index(name='count')
                print(df)
                if args.debug or args.counts:
                    print(value_counts_df)
                    # show column names
                    print("column names for value_counts")
                    print(list(value_counts_df))
                if args.generate_config:
                    # add to the map configs dataframe
                    print("generate configs for mapping/ranking for",r['column'])
                    for index, row in value_counts_df.iterrows():
                        map_config_df.loc[len(map_config_df)] = [ r['column'], row['value'] ,row['count'], '', '' ]
        if args.generate_config:
            # save the map configs dataframe as a "map-template" file in the source file directory
            map_config_df.to_csv(mapping_file + '.template', index=False)


    # create augmented columns for onehot, mapping, continuous, scaling, categories, rank
    if args.onehot or args.categories or args.continuous or args.scaling or args.group or args.rank:

        df = data[sourcefile['name']]

        # loop through each column and process any configured options
        for i, r in dictionary.iterrows():

            column_name = r['column']

            # get mapping subset for this column, if any (dictionary column name == mapping column name)
            map_col_df = map_config_df.loc[map_config_df['column'] == column_name]
            map_col_df = map_col_df.drop(columns={'column', 'frequency'}, axis=1)
            # drop columns we don't need, rename as appropriate
            map_col_df.rename(columns={'value': column_name }, inplace=True)
            if r['rank'] == False:
                map_col_df = map_col_df.drop('rank', axis=1)
            else:
                map_col_df.rename(columns={'rank': column_name + '_rank'}, inplace=True)

            if r['group'] == False:
                map_col_df = map_col_df.drop('group', axis=1)
            else:
                map_col_df.rename( columns={'group': column_name + '_grp'}, inplace=True)

            if args.debug:
                print("Map config for column:",column_name)
                print(map_col_df)

            # onehot encoding
            if args.onehot and r['onehot'] == True:
                one_hot_encoded = pd.get_dummies(df[r['column']], prefix=one_hot_prefix)
                df = pd.concat([df, one_hot_encoded], axis=1)

            # categories/label encoding
            if args.categories and r['category'] == True:
                encoder = LabelEncoder()
                encoded_column_name = categories_prefix + '_' + column_name
                df[encoded_column_name] = encoder.fit_transform(df[column_name])

            # ordinal encoding
            if (args.rank and r['rank'] == True and len(map_col_df.index) > 0) or (args.group and r['group'] == True and len(map_col_df.index) > 0):
                encoded_column_name = rank_prefix + '_' + column_name
                # df[encoded_column_name] = df.apply(lambda row: map_col_df.loc[map_col_df['value'] == row[column_name], 'rank'], axis=1)
                df = pd.merge(
                    left=df,
                    right=map_col_df,
                    left_on=column_name,
                    right_on=column_name,
                    how='left',
                    suffixes=('','_'+column_name)
                )
                if args.info:
                    print("Merged for rank/group:", df)
                # TODO: do we then normalize or scale the values afterwards, is that a separate option?

            # continuous
            #  z-score?  https://www.analyticsvidhya.com/blog/2015/11/8-ways-deal-continuous-variables-predictive-modeling/
            #  log transformation
            # https://www.freecodecamp.org/news/feature-engineering-and-feature-selection-for-beginners/
            # min-max Normalization (https://www.freecodecamp.org/news/feature-engineering-and-feature-selection-for-beginners/)
            # standardization (https://www.freecodecamp.org/news/feature-engineering-and-feature-selection-for-beginners/)

            # scaling

            # TODO: add a field level "missing" configuration to specify a strategy for handling missing sources
            # N/A, null, Empty, ?, none, empty, -, NaN, etc.
            # Strategies: variable deletion, mean/median imputation, most common value, ???

            # copy back to our data array
            data[sourcefile['name']] = df

    if args.info:
        print("Data:", data[sourcefile['name']])

# show the dictionary
if args.debug:
    print("Columns:",args.columns)
    print("Dictionary:",dictionary)

# merge selected source files by join-group
# exit(0)
# try using merge to join sources
print("sources.keys:", data.keys())
# summarize our sources
for d in data.keys():
    print()
    print()
    print()
    print()
    print("columns for ",d,":")
    # print(sources[d].describe())
    print(data[d].columns.values.tolist())

    # TODO: ultimately we want a single file, not one per source so need to merge in this loop then output below
    # generate output file
    data[d].to_csv(args.output, index=False)

print()
print()
print()

exit(0)
# determine best configuration for pre-defining possible merges

print("Merging...")
merge1 = pd.merge(data['clinvar-variant-summary-summary'], data['clinvar-variant-summary-vrs'], left_on='VariationID', right_on='clinvar_variation_id')
merge2 = pd.merge(merge1, data['gencc-submissions-submissions'], left_on='GeneSymbol', right_on='gene_symbol')
merge3 = pd.merge(merge2, data['clingen-dosage-dosage'], left_on='gene_symbol', right_on='GENE SYMBOL')
print()
print()
print("merge3:")
print(merge3.describe())
print(merge3.head())
print(merge3.columns.values.tolist())
print(merge3.size)
# gene
# variation id
# allele id

# determine best configuration for column selection

