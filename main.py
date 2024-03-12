# local modules
import arguments
import helper
import download
import generate

# other libraries
import os
from os import access, R_OK
from os.path import isfile

import pandas as pd
import yaml
from sklearn.preprocessing import LabelEncoder
import logging

# TODO:
# ** divide major areas into functions and perhaps files for code clarity and maintainability
# ** do I need to use globals? try to eliminate
# ** fix error when downloading files that have no url configured (suggest manual download?)
# ** os.path.join() for cross platform compatibility
# ** check logic around needs_download during --force
# ** dig more into why "is True" not working as expected in one spot


# TODO:
#  ** look for missing or deprecated columns in data files as compared to dictionaries and mapping files
#    (e.g. recent addition of oncology data)
#    - does dictionary have all the columns, are dictionary columns all present in the file?
#    - are all mapping columns still present in the file?

# TODO:
#  ** when creating dictionary template: analyze column data and set category,
#       onehot, continuous, days, age, based on data types and frequency


#########################
#
# PROGRAM ARGUMENTS
#
#########################

args = arguments.parse()

if args.join and not args.sources:
    print("ERROR: must specify --sources when specifying --join. The sources list is the list of data sources to join.")
    exit(-1)


####################
#
# Logging setup
#
####################
numeric_level = getattr(logging, args.loglevel.upper(), None)
if not isinstance(numeric_level, int):
    raise ValueError('Invalid log level: %s' % args.loglevel)
logging.basicConfig(filename='python.log', encoding='utf-8', level=numeric_level)

# constants
one_hot_prefix = 'hot'
categories_prefix = 'cat'
ordinal_prefix = 'ord'
rank_prefix = 'rnk'
days_prefix = 'days'
age_prefix = 'age'
sources_path = './sources'

# if multiple joins are possible, choose highest precedence join column
join_precedence = ('variation-id', 'gene-symbol', 'hgnc-id')

pd.set_option('display.max_rows', 1000)
pd.set_option('display.max_columns', 1000)
pd.options.mode.copy_on_write = True  # will become default in Pandas 3


###############################
#
# GENERATE CONFIGURATION YML
#
###############################
config_yml = """--- # Source file description
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
  template: # Text template which can generate a new output column. Template fields {column name} use dictionary names.
"""
if args.generate_config:
    cnt = 0
    for root, dirs, files in os.walk(sources_path):
        for d in dirs:
            # TODO: Use os.path.join()
            yml = '{}/{}/{}'.format(sources_path, d, 'config.yml')
            if isfile(yml) and access(yml, R_OK):
                helper.debug("Found existing config.yml", yml)
            else:
                cnt = cnt + 1
                helper.debug("Need to create", yml)
                with open(yml, 'w') as file:
                    file.write(config_yml)
    if cnt == 0:
        helper.info("All data sources have a config.yml")
    else:
        helper.info("Created", cnt, "config.yml files.")

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
            # TODO: Use os.path.join()
            file = '{}/{}/{}'.format(sources_path, os.path.basename(root), f)
            configList += [file]
            helper.debug(file)

helper.debug("config file list:")
helper.debug(configList)

# load all the config files into a source list dataframe
sourcefiles = pd.DataFrame(columns=['name', 'path', 'url', 'download_file', 'file', 'gzip', 'header_row',
                                    'skip_rows', 'delimiter', 'quoting', 'strip_hash', 'md5_url', 'md5_file',
                                    'template'])

for c in configList:
    helper.debug("for c in configList: c=", str(c))
    # TODO: Use os.path.join()
    path = c.replace('/config.yml', '')  # path is everything but trailing /config.yml
    helper.debug("for c in configList: path=", path)
    with open(c, "r") as stream:
        try:
            config = yaml.safe_load(stream)[0]
            helper.debug("config:", str(c))
            helper.debug(config)
            # add to config dataframe
            sourcefiles.loc[len(sourcefiles)] = [
                config.get('name'), path, config.get('url'), config.get('download_file'),
                config.get('file'), config.get('gzip'), config.get('header_row'),
                config.get('skip_rows'), config.get('delimiter'), config.get('quoting'),
                config.get('strip_hash'), config.get('md5_url'), config.get('md5_file'),
                config.get('template')
            ]

        except yaml.YAMLError as exc:
            helper.critical(exc)
            exit(-1)

# annotate source list with helper columns
sourcefiles['dictionary'] = sourcefiles.apply(lambda x: 'dictionary.csv', axis=1)
sourcefiles['mapping'] = sourcefiles.apply(lambda x: 'mapping.csv', axis=1)

sourcefiles.set_index('name')

helper.debug(sourcefiles)


#########################
#
# SOURCE LIST FILTRATION
#
#########################

# validate sourcefile selections in arguments if any
if args.sources is None:
    sources = list(set(sourcefiles['name']))
else:
    sources = list(set(sourcefiles['name']) & set(args.sources))

# any invalid sources?
invsources = set(sources).difference(sourcefiles['name'])
if len(invsources) > 0:
    helper.error("Invalid source file specficied in --sources parameter: ", invsources)
    exit(-1)

helper.debug("Using source files: ", sources)

# restrict source list by command line option, if any
if args.sources:
    sourcefiles = sourcefiles.loc[sourcefiles['name'].isin(sources)]

helper.debug("Source configurations: ", sourcefiles)


#########################
#
# DOWNLOAD DATA FILES
#
#########################

if args.download:
    download.all(sourcefiles, args.force)

#########################
#
# FIELD CONFIG DICTIONARY
#
#########################


def generate_dictionary(srcfile):
    # TODO: analyze column data and set category, onehot, continuous, days, age, based on data types and frequency
    print("Creating dictionary template")
    # TODO: Use os.path.join()
    data_file = srcfile.get('path') + '/' + srcfile.get('file')
    separator_type = helper.get_separator(srcfile.get('delimiter'))
    df_data_loc = pd.read_csv(data_file,
                              header=srcfile.get('header_row'), sep=separator_type,
                              skiprows=helper.skip_array(srcfile.get('skip_rows')), engine='python',
                              quoting=srcfile.get('quoting'),
                              nrows=0,
                              on_bad_lines='warn')
    cols = df_data_loc.columns.tolist()
    # newcol = column.strip(' #')
    # create dataframe with appropriate columns
    df_dic = pd.DataFrame(columns=['column', 'comment', 'join-group', 'onehot', 'category',
                                   'continuous', 'format', 'map', 'days', 'age', 'expand', 'na-value'])
    # create one row per column header
    defaults = {'comment': '', 'join-group': '', 'onehot': 'FALSE', 'category': 'FALSE', 'continuous': 'FALSE',
                'format': '', 'map': 'FALSE', 'days': 'FALSE', 'age': 'FALSE', 'expand': 'FALSE', 'na-value': ''}
    for field in cols:
        df_dic.loc[len(df_dic)] = [field, defaults['comment'], defaults['join-group'], defaults['onehot'],
                                   defaults['category'], defaults['continuous'], defaults['format'], defaults['map'],
                                   defaults['days'], defaults['age'], defaults['expand']]
    # save dataframe as csv
    # TODO: Use os.path.join()
    dictemplate = srcfile.get('path') + '/dictionary.csv'
    df_dic.to_csv(dictemplate, index=False)
    helper.info("Created dictionary template", dictemplate)
    return ''


#  verify existence of source dictionaries
missing_dictionary = 0
for index, sourcefile in sourcefiles.iterrows():
    # TODO: Use os.path.join()
    dictionary_file = sourcefile.get('path') + '/' + sourcefile.get('dictionary')
    if isfile(dictionary_file) and access(dictionary_file, R_OK):
        helper.debug("Found dictionary file", dictionary_file)
    else:
        helper.warning("WARNING: Missing dictionary file", dictionary_file)
        missing_dictionary = missing_dictionary + 1
        if args.generate_config:
            generate_dictionary(sourcefile)

if missing_dictionary:
    if not args.generate_config:
        helper.critical(missing_dictionary, "missing dictionaries.",
                        "Use --generate-config to create template configurations.")
        exit(-1)
else:
    helper.debug("Verified all dictionaries exist.")

# setup sources dictionary
dictionary = pd.DataFrame(columns=['name', 'path', 'file', 'column', 'comment', 'join-group', 'onehot', 'category',
                                   'continuous', 'format', 'map', 'days', 'age', 'expand', 'na-value'])
data = dict()
global sourcecolumns, map_config_df

#  process each source file and dictionary
for index, sourcefile in sourcefiles.iterrows():

    helper.debug(sourcefile.get('path'), sourcefile.get('file'),
                 sourcefile.get('dictionary'), "sep='" + sourcefile.get('delimiter') + "'")

    separator = helper.get_separator(sourcefile.get('delimiter'))

    # read source dictionary
    helper.debug("Reading dictionary")
    helper.debug("sourcefile =", sourcefile)

    # TODO: Use os.path.join()
    dictionary_file = sourcefile.get('path') + '/' + sourcefile.get('dictionary')

    helper.info("Read dictionary", dictionary_file)

    dic = pd.read_csv(dictionary_file)

    helper.debug(dic)

    # add dictionary entries to global dic if specified on command line, or all if no columns specified on command line
    for i, r in dic.iterrows():
        if args.columns is None or r['column'] in args.columns:
            dictionary.loc[len(dictionary)] = [sourcefile.get('name'),
                                               sourcefile.get('path'), sourcefile.get('file'), r.get('column'),
                                               r.get('comment'), r.get('join-group'), r.get('onehot'),
                                               r.get('category'), r.get('continuous'), r.get('format'), r.get('map'),
                                               r.get('days'), r.get('age'), r.get('expand'), r.get('na-value')]

    helper.debug("Dictionary processed")

    # read source sources
    helper.info("Reading source for", sourcefile.get('name'), "...")

    # TODO: Use os.path.join()
    sourcefile_file = sourcefile.get('path') + '/' + sourcefile.get('file')

    if args.columns is None:
        df_tmp = pd.read_csv(sourcefile_file,
                             header=sourcefile.get('header_row'), sep=separator,
                             skiprows=helper.skip_array(sourcefile.get('skip_rows')), engine='python',
                             quoting=sourcefile.get('quoting'),
                             # nrows=100,
                             on_bad_lines='warn')
        helper.debug("File header contains columns:", df_tmp.columns)
        data.update({sourcefile['name']: df_tmp})
        sourcecolumns = list(set(dic['column']))
    else:
        sourcecolumns = list(set(dic['column']) & set(args.columns))
        data.update({sourcefile['name']: pd.read_csv(sourcefile_file,
                                                     #  usecols=sourcecolumns,
                                                     usecols=lambda x: x.strip(' #') in sourcecolumns,
                                                     header=sourcefile.get('header_row'), sep=separator,
                                                     skiprows=helper.skip_array(sourcefile.get('skip_rows')),
                                                     engine='python',
                                                     quoting=sourcefile.get('quoting'),
                                                     # nrows=100,
                                                     on_bad_lines='warn')})
    if sourcefile['strip_hash'] == 1:
        helper.debug("Strip hashes and spaces from column labels")
        df = data[sourcefile.get('name')]
        # rename columns
        for column in df:
            newcol = column.strip(' #')
            if newcol != column:
                helper.debug("Stripping", column, "to", newcol)
                data[sourcefile['name']] = df.rename({column: newcol}, axis='columns')
            else:
                helper.debug("Not stripping colum", column)
        helper.debug(data[sourcefile['name']])
    else:
        helper.debug("Not stripping column labels")

    if args.expand:
        helper.debug("name:", sourcefile['name'])
        helper.debug("dictionary:")
        helper.debug(dic)
        dic_filter_df = dic.loc[(dic.get('expand') == True)]
        if len(dic_filter_df) > 0:
            helper.debug("Found", len(dic_filter_df), "columns to expand.")
            sourcename = sourcefile.get('name')
            df = data[sourcename]
            helper.debug("expand columns for", sourcename, "length", len(df))
            for i, r in dic_filter_df.iterrows():
                col_name = r['column']
                helper.debug("expanding column", col_name)
                expandable_rows_df = df.loc[(df.get(col_name).str.contains(","))]
                # for each row, create a copy with each value
                for exp_i, exp_r in expandable_rows_df.iterrows():
                    values = exp_r[col_name].split(",")
                    for v in values:
                        new_row = expandable_rows_df.loc[exp_i].copy()
                        new_row[col_name] = v
                        df.loc[len(df)] = new_row
            helper.debug("new length", len(df))
            data[sourcename] = df

    # is there an optimal spot to filter for gene and variant?
    if args.gene:
        helper.debug("filter genes", args.gene)
        dic_filter_df = dic.loc[(dic['join-group'] == 'gene-symbol')]
        if len(dic_filter_df) > 0:
            df = data[sourcefile['name']]
            helper.debug("filter columns with gene-symbol join group and value", args.gene,
                         "for", sourcefile['name'], "length", len(df))
            for i, r in dic_filter_df.iterrows():
                col_name = r['column']
                genes = args.gene.split(',')
                helper.debug("filtering column", col_name, " in ", genes)
                df = df.loc[(df[col_name].isin(genes))]
            helper.debug("new length", len(df))
            data[sourcefile['name']] = df

    if args.variant:
        helper.debug("filter variant", args.variant)
        dic_filter_df = dic.loc[(dic['join-group'] == 'variation-id')]
        if len(dic_filter_df) > 0:
            df = data[sourcefile['name']]
            helper.debug("filter columns with variation-id join group and value", args.variant,
                         "for", sourcefile['name'], "length", len(df))
            for i, r in dic_filter_df.iterrows():
                col_name = r['column']
                variants = map(int, args.variant.split(','))
                helper.debug("filtering column", col_name, " = ", args.variant, variants)
                df = df.loc[df[col_name].isin(variants)]
            helper.debug("new length", len(df))
            data[sourcefile['name']] = df

    # show count of unique values per column
    if args.counts:
        print(sourcefile['name'], ":", data[sourcefile['name']].nunique())
        print("Finshed reading source file")
        print()
        print()

    # read mapping file, if any, and filter by selected columns, if any
    # TODO: Use os.path.join()
    mapping_file = sourcefile['path'] + '/' + 'mapping.csv'
    map_config_df = pd.DataFrame()
    if not args.generate_config:
        map_config_df = pd.read_csv(mapping_file)
        map_config_df = map_config_df.loc[map_config_df['column'].isin(sourcecolumns)]

        helper.debug("Mapping Config:", map_config_df)

    # for rank and group mapping columns, show the counts of each value
    if args.counts:
        # loop through each column that has rank and/or group set to True
        # sourcecolumns has list of columns to sift through for settings
        if args.generate_config:
            # create map configs dataframe to collect the values
            map_config_df = pd.DataFrame(
                columns=['column', 'value', 'frequency', 'map-name', 'map-value']
            )
        df = data[sourcefile['name']]
        for i, r in dic.iterrows():
            if r['map'] is True:
                print()
                print("unique values and counts for", sourcefile['path'], sourcefile['file'], r['column'])
                value_counts_df = df[r['column']].value_counts().rename_axis('value').reset_index(name='count')
                helper.debug(df)
                helper.debug(value_counts_df)
                if args.counts:
                    print(value_counts_df)

                if args.generate_config:
                    # add to the map configs dataframe
                    helper.debug("generate configs for mapping/ranking for", r['column'])
                    for ind, row in value_counts_df.iterrows():
                        map_config_df.loc[len(map_config_df)] = [r['column'], row['value'], row['count'], '', '']
        if args.generate_config:
            # save the map configs dataframe as a "map-template" file in the source file directory
            map_config_df.to_csv(mapping_file + '.template', index=False)

    # create augmented columns for onehot, mapping, continuous, scaling, categories, rank
    if args.onehot or args.categories or args.map:  # or args.continuous or args.scaling

        df = data[sourcefile['name']]
        helper.debug("Processing onehot, mapping, etc. for", sourcefile['name'], "df=", df)

        # loop through each column and process any configured options
        # for i, r in dictionary.iterrows():
        for i, r in dic.iterrows():

            column_name = r['column']

            #
            # mappings
            #
            if args.map and r['map'] is True:

                # get mapping subset for this column, if any (dictionary column name == mapping column name)
                map_col_df = map_config_df.loc[map_config_df['column'] == column_name]
                map_col_df = map_col_df.drop(columns={'column', 'frequency'}, axis=1)
                map_col_df.rename(columns={'value': column_name}, inplace=True)

                helper.debug("Map config for column:", column_name)
                helper.debug(map_col_df)

                # get list of unique 'map-name' values
                map_names = map_col_df['map-name'].unique()

                # loop through each 'map-name'
                if len(map_names) > 0 and len(map_col_df.index) > 0:

                    for m in map_names:

                        # create filtered dataframe for map-name
                        map_name_df = map_col_df.loc[(map_col_df['map-name'] == m)]
                        map_name_df = map_name_df.drop(columns={'map-name'}, axis=1)

                        # rename map-value as the value of map-name in the sub-filtered dataframe
                        map_name_df.rename(columns={'map-value': m}, inplace=True)

                        # merge based on column-name
                        df[column_name] = df[column_name].astype(str)
                        map_name_df[column_name] = map_name_df[column_name].astype(str)
                        df = pd.merge(
                            left=df,
                            right=map_name_df,
                            left_on=column_name,
                            right_on=column_name,
                            how='left',
                            suffixes=(None, '_remove')
                        )
                        # get rid of duplicated columns from join
                        df.drop(df.filter(regex='_remove$').columns, axis=1, inplace=True)

            #
            # onehot encoding
            #
            if args.onehot and r['onehot'] is True:
                helper.debug("One-hot encoding", column_name, "as", one_hot_prefix+column_name)
                oh_prefix = column_name + '_' + one_hot_prefix + '_'
                one_hot_encoded = pd.get_dummies(df[column_name], prefix=oh_prefix)
                df = pd.concat([df, one_hot_encoded], axis=1)

            #
            # categories/label encoding
            #
            if args.categories and r['category'] is True:
                encoder = LabelEncoder()
                encoded_column_name = categories_prefix + '_' + column_name
                helper.debug("Category encoding", column_name, "as", encoded_column_name)
                helper.debug("Existing values to be encoded:", df)
                df[encoded_column_name] = encoder.fit_transform(df[column_name])

                # TODO: do we then normalize or scale the values afterwards, is that a separate option?

            # date time encodings (age, days)
            if not pd.isna(r['format']):
                helper.debug("Age/Days: Column=", column_name, " format=", r['format'])
                if args.age:
                    age_column = age_prefix + '_' + column_name
                    df[age_column] = df.apply(lambda x: helper.get_age(x.get(column_name), r['format']), axis=1)
                if args.days:
                    days_column = days_prefix + '_' + column_name
                    df[days_column] = df.apply(lambda x: helper.get_days(x.get(column_name), r['format']), axis=1)

            # column-level NaN value replacement
            if not pd.isna(r['na-value']) and r['na-value'] is not None:
                helper.debug("Apply na-value", r['na-value'], "to", column_name)
                df.fillna({column_name: r['na-value']}, inplace=True)

            # Strategies: variable deletion, mean/median imputation, most common value, ???
            # continuous
            #  z-score?
            #   (https://www.analyticsvidhya.com/blog/2015/11/8-ways-deal-continuous-variables-predictive-modeling/)
            #  log transformation
            #   (https://www.freecodecamp.org/news/feature-engineering-and-feature-selection-for-beginners/)
            # min-max Normalization
            #   (https://www.freecodecamp.org/news/feature-engineering-and-feature-selection-for-beginners/)
            # standardization
            #   (https://www.freecodecamp.org/news/feature-engineering-and-feature-selection-for-beginners/)

            # scaling

        # if specified, fill any remaining N/A values that weren't filled in at the field level
        if args.na_value is not None:
            df.fillna(args.na_value, inplace=True)

        # copy back to our data array
        data[sourcefile['name']] = df

    if args.template and len(sourcefile['template']) > 0:
        sourcefile_name = sourcefile['name']
        template_column_name = "{}-template".format(sourcefile_name)
        helper.debug("Applying template to", sourcefile_name, "as", template_column_name)
        df = data[sourcefile_name]
        df[template_column_name] = df.apply(lambda x: helper.apply_template(sourcefile['template'], x), axis=1)
        data[sourcefile_name] = df

    helper.debug("Data:", data[sourcefile['name']])

# show the dictionary
helper.debug("Columns:", args.columns)
helper.debug("Dictionary:", dictionary)


#########################
#
# PER-SOURCE OUTPUT
#
#########################

# create per-source output files to debugging purposes
if args.individual:
    helper.debug("sources.keys:", data.keys())
    helper.debug("sourcefiles:", sourcefiles)

    # summarize our sources
    for d in data.keys():
        helper.debug("columns for ", d, ":")
        helper.debug(data[d].columns.values.tolist())

        # files put in current directory, prepend source name to file
        output_file = d + '-' + args.output
        helper.debug("Generating intermediate source output", output_file)
        out_df = data[d]
        helper.debug("out_df:", out_df)
        out_df.to_csv(output_file, index=False)


#########################
#
# MERGED OUTPUT
#
#########################

# merge selected source files by join-group
# only merge if sources specified on command line (--sources)
if args.join:
    if args.sources:
        # merge by order of sources specified on command line using left joins in sequence
        helper.info("Merging data sources:", args.sources)
        sources_sort = list(args.sources)

        dic_df = dictionary[dictionary['join-group'].notnull()]
        dic_df['precedence'] = dic_df.apply(lambda x: helper.get_join_precedence(x.get('join-group')), axis=1)
        out_df = pd.DataFrame()
        already_joined_dic_df = pd.DataFrame(data=None, columns=dictionary.columns)
        c = 0
        for s in sources_sort:
            helper.info("Merging", s)
            # get join columns for s
            s_dic_df = dic_df.loc[(dic_df['name'] == s)].sort_values(by=['precedence'])
            # s_join_columns = filter dictionary by s and join-group not null
            if c == 0:
                out_df = data[s]
            else:
                # pick a join group that has already in a merged dataset, starting with the highest precedence
                join_groups = s_dic_df['join-group'].unique()
                helper.debug("joins for", s, "include", join_groups)
                helper.debug("prior join groups:", already_joined_dic_df)
                selected_join_group = None
                for jg in join_groups:
                    helper.debug("checking if previous merges have", jg)
                    if len(already_joined_dic_df.loc[(already_joined_dic_df['join-group'] == jg)]) == 0:
                        continue
                    selected_join_group = jg
                    break
                if selected_join_group is None:
                    helper.error("Didn't find a matching prior join-group for", s)
                    exit(-1)
                # get the left and right join column names for selected join group
                left_join_df = already_joined_dic_df.loc[(already_joined_dic_df['join-group']
                                                          == selected_join_group)].iloc[0]
                left_join_column = left_join_df['column']
                helper.debug("Left join column", left_join_column)

                right_join_df = s_dic_df.loc[(s_dic_df['join-group'] == selected_join_group)].iloc[0]
                right_join_column = right_join_df['column']
                helper.debug("Right join column", right_join_column)
                helper.debug("Out length prior", len(out_df))
                out_df = pd.merge(out_df, data[s], how='left', left_on=left_join_column, right_on=right_join_column)
                helper.debug("Out length after", len(out_df))
            c = c + 1
            helper.debug("Adding to prior join df", s_dic_df)
            already_joined_dic_df = pd.concat([already_joined_dic_df, s_dic_df])
            helper.debug("Now prior join df:")
            helper.debug(already_joined_dic_df)

        # fill in any Nan values after merging dataframes
        if args.na_value is not None:
            out_df.fillna(args.na_value, inplace=True)

        output_file = args.output
        helper.info("Generating output", output_file)
        helper.debug("out_df:", out_df)
        out_df.to_csv(output_file, index=False)
    else:
        helper.error("ERROR: --join requires at least one source specified with --sources parameter.")
        exit(-1)

helper.info("Exiting")

exit(0)
