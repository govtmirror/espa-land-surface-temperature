#! /usr/bin/env python

'''
    PURPOSE: Retrieves archived NARR files from the NCEP for the dates
             requested.  Extracts the variables LST requires (HGT, TMP, SPFH)
             and repackages them into our internal location and filenames.

    PROJECT: Land Satellites Data Systems Science Research and Development
             (LSRD) at the USGS EROS

    LICENSE: NASA Open Source Agreement 1.3

    NOTES:

          NCEP     - National Centers for Environmental Prediction
                     http://www.ncep.noaa.gov

          NARR     - NCEP North American Regional Reanalysis

          CISL RDA - Computational & Information Systems Lab
                     Research Data Archive http://rda.ucar.edu

          NCAR     - National Center for Atmospheric Research
                     http://ncar.ucar.edu

          UCAR     - University Corporation for Atmospheric Research
                     http://www2.ucar.edu
'''

import os
import sys
import shutil
import logging
import errno
import commands
import requests
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from time import sleep
from datetime import datetime, timedelta, date
from contextlib import closing
import collections
import json


# ============================================================================
class Web(object):
    '''
    Description:
        Provides methods for interfacing with web resources.
    '''

    # ------------------------------------------------------------------------
    class Session(object):
        '''
        Description:
            Manages an http(s) session.
        '''

        # --------------------------------------------------------------------
        def __init__(self, max_retries=3, block_size=None, timeout=300.0):
            super(Web.Session, self).__init__()

            self.logger = logging.getLogger(__name__)

            self.session = requests.Session()

            self.timeout = timeout
            self.max_retries = max_retries
            self.status_code = requests.codes['ok']

            # Determine if we are streaming or not based on block_size
            self.block_size = block_size
            self.stream = False
            if self.block_size is not None:
                self.stream = True

            adapter = requests.adapters.HTTPAdapter(max_retries=max_retries)
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)

        # --------------------------------------------------------------------
        def login(self, login_url, login_data):
            '''
            Description:
                Provides for establishing a logged in session.
            '''

            # Login to the site
            self.session.post(url=login_url, data=login_data)

        # --------------------------------------------------------------------
        def _get_file(self, download_url, destination_file, headers=None):
            '''
            Notes: Downloading this way will place the whole source file into
                   memory before dumping to the local file.
            '''

            with closing(self.session.get(url=download_url,
                                          timeout=self.timeout,
                                          headers=headers)) as req:

                self.status_code = req.status_code

                if not req.ok:
                    self.logger.error('HTTP - Transfer of [{0}] - FAILED'
                                      .format(download_url))
                    # The raise_for_status generates an exception to be caught
                    req.raise_for_status()

                # Write the downloaded data to the destination file
                with open(destination_file, 'wb') as local_fd:
                    local_fd.write(req.content)

        # --------------------------------------------------------------------
        def _stream_file(self, download_url, destination_file, headers=None):
            '''
            Notes: Downloading this way streams 'block_size' of data at a
                   time.
            '''

            retrieved_bytes = 0
            with closing(self.session.get(url=download_url,
                                          timeout=self.timeout,
                                          stream=True,
                                          headers=headers)) as req:
                self.status_code = req.status_code

                if not req.ok:
                    self.logger.error('HTTP - Transfer of [{0}] - FAILED'
                                      .format(download_url))
                    # The raise_for_status generates an exception to be caught
                    req.raise_for_status()

                file_size = int(req.headers['content-length'])

                # Set block size based on streaming
                if self.stream:
                    block_size = self.block_size
                else:
                    block_size = file_size

                # Write the downloaded data to the destination file
                with open(destination_file, 'wb') as local_fd:
                    for data_chunk in req.iter_content(block_size):
                        local_fd.write(data_chunk)
                        retrieved_bytes += len(data_chunk)

                if retrieved_bytes != file_size:
                    raise Exception('Transfer Failed - HTTP -'
                                    ' Retrieved {0} out of {1} bytes'
                                    .format(retrieved_bytes, file_size))

        # --------------------------------------------------------------------
        def http_transfer_file(self, download_url, destination_file):
            '''
            Description:
                Use http to transfer a file from a source location to a
                destination file on the localhost.
            Returns:
                status_code - One of the following
                            - 200, requests.codes['ok']
                            - 404, requests.codes['not_found']:
                            - 503, requests.codes['service_unavailable']:
            Notes:
                If a 503 is returned, the logged exception should be reviewed
                to determine the real cause of the error.
            '''

            self.logger.info(download_url)

            retry_attempt = 0
            done = False
            while not done:
                self.status_code = requests.codes['ok']
                try:

                    self._stream_file(download_url, destination_file)

                    self.logger.info("Transfer Complete - HTTP")
                    done = True

                except Exception:
                    self.logger.exception('HTTP - Transfer Issue')

                    if self.status_code not in (requests.codes['not_found'],
                                                requests.codes['forbidden']):

                        if retry_attempt > self.max_retries:
                            self.logger.info('HTTP - Transfer Failed'
                                             ' - exceeded retry limit')
                            done = True
                        else:
                            retry_attempt += 1
                            sleep(int(1.5 * retry_attempt))
                    else:
                        # Not Found - So break the looping because we are done
                        done = True

            return self.status_code

        # --------------------------------------------------------------------
        def get_lines_from_url(self, download_url):
            '''retrieve lines from a url'''

            data = []
            self.status_code = requests.codes['ok']

            with closing(self.session.get(url=download_url,
                                          timeout=self.timeout,
                                          stream=self.stream)) as req:
                self.status_code = req.status_code

                if not req.ok:
                    self.logger.error('HTTP - Transfer of [{0}] - FAILED'
                                      .format(download_url))
                    # The raise_for_status generates an exception to be caught
                    req.raise_for_status()

                for line in req.iter_lines():
                    data.append(line)

            return data


# ============================================================================
class System(object):
    '''
    Description:
        Provides methods for interfacing with the host server.
    '''

    # ------------------------------------------------------------------------
    @staticmethod
    def execute_cmd(cmd):
        '''
        Description:
            Execute a command line and return the terminal output or raise an
            exception

        Returns:
            output - The stdout and/or stderr from the executed command.
        '''

        logger = logging.getLogger(__name__)

        output = ''

        logger.info('Executing [{0}]'.format(cmd))
        (status, output) = commands.getstatusoutput(cmd)

        if status < 0:
            message = 'Application terminated by signal [{0}]'.format(cmd)
            if len(output) > 0:
                message = ' Stdout/Stderr is: '.join([message, output])
            raise Exception(message)

        if status != 0:
            message = 'Application failed to execute [{0}]'.format(cmd)
            if len(output) > 0:
                message = ' Stdout/Stderr is: '.join([message, output])
            raise Exception(message)

        if os.WEXITSTATUS(status) != 0:
            message = ('Application [{0}] returned error code [{1}]'
                       .format(cmd, os.WEXITSTATUS(status)))
            if len(output) > 0:
                message = ' Stdout/Stderr is: '.join([message, output])
            raise Exception(message)

        return output

    # ------------------------------------------------------------------------
    @staticmethod
    def create_directory(directory):
        '''
        Description:
            Create the specified directory with some error checking.
        '''

        # Create/Make sure the directory exists
        try:
            os.makedirs(directory, mode=0755)
        except OSError as ose:
            if ose.errno == errno.EEXIST and os.path.isdir(directory):
                pass
            else:
                raise


class Config(object):
    '''Provides access to configurable attributes of script

    Provides transparent access to settings from configuration
        1.Settings can specified as a json object stored in a file.
            read_config will be used to insert these into Config.config dict.
        2.Settings can be defined in the dictionary, Config.config, as
            key/value pairs.
        3.Settings can be defined in the default_config.
    Beware: read_config will overwrite the contents of the configuration file
 ftp://ftp.cpc.ncep.noaa.gov/NARR/archive/rotating_3hour/{0}
'http://ftp.cpc.ncep.noaa.gov/wd51we/NARR_archive/{0}'),
    '''
    config = None  # Stores result of reading json object from file.
    default_config = {'ncep_url_format':
                      'http://broken/broken/broken/{0}',
                      'remote_name_format':
                          'rcdas.{0:03}{1:02}{2:02}{3:02}.awip32.merged',
                      'archive_directory_format':
                          '{0}/{1:0>4}/{2:0>2}/{3:0>2}',
                      'archive_name_format':
                          'NARR_3D.{0}.{1:04}{2:02}{3:02}.{4:04}.{5}'}

    @classmethod
    def read_config(cls, cfg_file='lst_auxillary.config'):
        '''Reads configurable options from a file in current directory

        Note: By default the function will read a file but otherwise
            another file could be indicated via parameter cfg_file
        Precondition:
            Assumes a JSON data object, this is defined by json module.
                json.loads is able to parse the contents of the file
            Any line that starts with '#' will be ignored.
        Postcondition:
            dictionary representing the JSON object is stored in memeory
            Config.config is stored as a class variable
            Raises Exception if json object can't be parsed
        '''
        with open(cfg_file, 'r') as cfg_fd:
            lines = list()
            for line in cfg_fd:
                # Skip rudimentary comments
                if line.strip().startswith('#'):
                    continue

                lines.append(line)

            cls.config = json.loads(' '.join(lines))

        if cls.config is None:
            raise Exception('Failed loading configuration')

        return cls.config

    @classmethod
    def get(cls, attr):
        '''Get value of configurable setting from a file or default

            First it will try to read json data from the config file.
            If file does not exist then onfig will be from default values.
            If Key/value pair doesn't exist in JSON-like object stored in the
                file then default values will be used.
        '''
        value = None
        logger = logging.getLogger(__name__)
        try:
            if cls.config is None:
                cls.config = cls.read_config()
            if attr in cls.config:
                value = cls.config[attr]
                logger.info('Using value({0}) from config file for {1}.'
                            .format(value, attr))
                value = cls.config[attr]
            else:
                logger.warn('Using default value({0}) for {1}.'.format(value,
                                                                       attr))
                value = cls.default_config[attr]
        except IOError:
            # If no config is read then use defaults
            value = cls.default_config[attr]

        return value


class Ncep(object):
    '''Interface for interacting with Ncep website

    NarrData depends on the following functionality of this class:
        Provide means of getting a particular grib file into current working
            directory via get_grib_file()
        Provides a dict of all files available via get_dict_of_date_modified()
            keys are filenames, values are time of last modification
        Provides format of the grib filename via get_filename()
    '''
    mtime_by_name = None
    session = None

    @staticmethod
    def get_url(filename):
        '''TODO TODO TODO'''
        return Config.get('ncep_url_format').format(filename)

    @staticmethod
    def get_filename(year, month, day, hour):
        '''TODO TODO TODO'''
        fmt = Config.get('remote_name_format')
        return fmt.format(year, month, day, hour)

    @staticmethod
    def get_datetime_from_filename(filename):
        '''Extracts tuple (year, month, day, hour) from filename

        Precondition:
            File is of format "rcdas.2015081321.awip32.merged" for the
                measurement at 21:00 (9pm) on August 13th and similar for all
                other measurements
        Postcondition:
            Returns datetime object of the time when the measurement took place
        '''
        return datetime.strptime(filename.split('.')[1],
                                 '%Y%m%d%H')

    @classmethod
    def get_grib_file(cls, filename):
        '''

        Precondition:
            File with "filename" exists on the NCEP website.
            "get_url" will return address of file on website
            "get_last_modified" returns a datetime object
                This datetime object should be the last time the item was
                updated on the website.
            File does not exists in current directory
        Postcondition:
            grib_file associated with this filename is in current directory
            Logs the last modified time of file and the address used.
            If file already exists then only an info message will be recorded.
        '''
        logger = logging.getLogger(__name__)

        if os.path.isfile(filename):
            logger.info('{0} already exists. Skipping download.'
                        .format(filename))
        else:
            logger.info('Retrieving {0}'.format(filename))
            cls.get_session().http_transfer_file(cls.get_url(filename),
                                                 filename)

    @classmethod
    def get_list_of_external_data(cls):
        '''Retrieves list of available data from website's directory listing

        Sample line from url reqest the list of files (single line):
        '<tr><td><a href="rcdas.2015010300.awip32.merged.b">
            rcdas.2015010300.awip32.merged.b</a></td>
        <td align="right">08-Jan-2015 10:12  </td>
        <td align="right">1.3M</td></tr>\n'
        '''
        archive_data = collections.namedtuple('ArchiveData',
                                              ['name', 'mtime', 'size'])

        lines_thrown = 0
        data_list = []

        custom_session = cls.get_session()
        try:
            data = custom_session.get_lines_from_url(Ncep.get_url(''))

            for line in data:
                if 'awip' not in line:
                    lines_thrown = lines_thrown + 1
                    continue  # go to next line

                (garbage, partial_line) = line.split('">', 1)
                (name, partial_line) = partial_line.split('</a>', 1)
                (garbage, partial_line) = partial_line.split('">', 1)
                (mtime, partial_line) = partial_line.split('</td>', 1)
                (garbage, partial_line) = partial_line.split('">', 1)
                (size, partial_line) = partial_line.split('</td>', 1)

            mtime = mtime.strip()  # Remove extra space
            data_list.append(archive_data(name=name, mtime=mtime, size=size))

        except Exception:
            raise

        return data_list

    @classmethod
    def get_session(cls):
        '''Obtains and then retains session used for downloading'''
        if cls.session is None:
            # Establish a logged in session
            cls.session = Web.Session()
        return cls.session

    @classmethod
    def get_dict_of_date_modified(cls):
        '''Returns a dictionary of mtime for ext. files with filename as key

        Note:
            If the dictionary has been cached then use it otherwise create it.
        Precondition:
            Requires that get_list_of_external_data() returns list containing
                NamedTuples with tuple.mtime and tuple.name defined.
        Postcondition: Returns a dictionary
            filename as key, external last modified time as value
        '''
        if cls.mtime_by_name is None:
            data_list = Ncep.get_list_of_external_data()
            cls.mtime_by_name = {}
            for item in data_list:
                date_modified = datetime.strptime(item.mtime,
                                                  '%d-%b-%Y %H:%M')
                cls.mtime_by_name[item.name] = date_modified

        return cls.mtime_by_name


class NarrData(object):
    '''TODO TODO TODO'''
    variables = ['HGT', 'TMP', 'SPFH']  # Variables that will be extracted

    class FileMissing(Exception):
        '''Exception raised when file is missing internally or on website'''
        pass

    def __init__(self, year, month, day, hour=00):
        hour = hour/3*3  # Ensures it is a multiple of 3
        self.dt = datetime(year, month, day, hour=hour)
        logger = logging.getLogger(__name__)
        logger.info('---- {0} {1} {2} {3}'.format(year, month, day, hour))

    @staticmethod
    def from_external_name(external_name):
        '''Creates NarrData object from name of external file'''
        date_measured = Ncep.get_datetime_from_filename(external_name)

        return NarrData(year=date_measured.year, month=date_measured.month,
                        day=date_measured.day, hour=date_measured.hour)

    @staticmethod
    def get_next_narr_data_gen(s_date, e_date, interval=timedelta(hours=3)):
        '''Generator to iterate through NarrData objects in time interval

        Note: time of datetime objects is ignored.
            start of day is used for s_date and end of day for e_date.
        Precondition:
            s_date and e_date are of type datetime.datetime
            s_date and e_date can also be of type datetime.date
            interval is of type datetime.timedelta
        Postcondition: Returns NarrData instance
            s_date < datetime of NarrData < e_date
            Consider narr[i-1], narr[i], narr[i+1] as previous, current and
                next values of iterator. The following statement will be true:
                narr[i-1].dt + interval == narr[i].dt == narr[i].dt - interval
        '''
        try:  # Handles if datetime objects are passed in.
            start_time = datetime.combine(s_date.date(), datetime.min.time())
            end_time = datetime.combine(e_date.date(), datetime.max.time())
        except AttributeError:  # Handles if date objects are passed in.
            start_time = datetime.combine(s_date, datetime.min.time())
            end_time = datetime.combine(e_date, datetime.max.time())

        logger = logging.getLogger(__name__)
        logger.info('Generating list of data from {0} to {1}'
                    .format(start_time.isoformat(), end_time.isoformat()))

        current = NarrData(year=start_time.year, month=start_time.month,
                           day=start_time.day, hour=start_time.hour)
        while current.dt <= end_time:
            yield current
            current = current.get_next(interval)

    def get_internal_drectory(self):
        '''TODO TODO TODO'''
        return NarrArchive.get_arch_dir(self.dt.year, self.dt.month,
                                        self.dt.day)

    def get_internal_filename(self, variable, ext):
        '''TODO TODO TODO'''
        return NarrArchive.get_arch_filename(variable, self.dt.year,
                                             self.dt.month, self.dt.day,
                                             self.dt.hour, ext)

    def get_internal_last_modified(self, variable='HGT', ext='hdr'):
        '''Stat internal file for mtime. Default to HGT's hdr file.

        Precondition:
            File must exist at path given by get_internal_filepath
        Postcondition:
            returns time of last modification of internal file
            raises NarrData.FileMissing if precondition is violated
        '''
        try:
            filepath = os.path.join(self.get_internal_drectory(),
                                    self.get_internal_filename(variable, ext))
            ts_epoch = os.stat(filepath).st_mtime
            mtime = datetime.fromtimestamp(ts_epoch)
        except OSError:  # Expecting 'No such file or directory'
            raise NarrData.FileMissing

        return mtime

    def get_external_filename(self):
        '''Returns the name of the grib file as choosen by data source'''
        return Ncep.get_filename(self.dt.year, self.dt.month, self.dt.day,
                                 self.dt.hour)

    def get_external_last_modified(self):
        '''Returns last_modified time from dictionary stored in Ncep

        Precondition:
            Ncep class must be able to obtain list of data from website.
            filename must exist as key in dict of date modified
        Postcondition:
            returns date of last modification of the entry with filename as key
            Raises NarrData.FileMissing if either precondition is violated.
        '''
        filename = self.get_external_filename()

        try:
            # Last modified time according to http table on website
            table_last_mod = Ncep.get_dict_of_date_modified()[filename]
        except KeyError:
            raise NarrData.FileMissing

        return table_last_mod

    def need_to_update(self):
        '''Returns boolean of whether file neads to be donwloaded

        Precondition:
            get_internal_last_modified and get_external_last_modified return
                value of type datetime.
        Postcondition:
            returns True if either of these conditions are true:
                (1) Internal copy of file is older than remote copy
                (2) Internal file is missing
            returns False if either of these conditions are true:
                (1) Internal modified time is more recent then external
                    modified time
                (2) External file is missing
        '''
        logger = logging.getLogger(__name__)
        try:
            ext_mtime = self.get_external_last_modified()
        except NarrData.FileMissing:  # Expecting 'No such file or directory'
            logger.debug('{0} is missing from list of external files'
                         .format(self.get_external_filename()))
            return False  # File is not available to download

        try:
            # Check if existing data is stale
            return self.get_internal_last_modified() < ext_mtime
        except NarrData.FileMissing:  # Expecting 'No such file or directory'
            return True  # The file does not exist internally.

    def get_grib_file(self):
        '''TODO TODO TODO'''
        Ncep.get_grib_file(self.get_external_filename())

    def extract_vars_from_grib(self):
        '''process_grib_for_variable for each var in NarrData.variables'''
        for var in NarrData.variables:
            self.process_grib_for_variable(var)

    def move_files_to_archive(self):
        '''move_to_archive for each var in NarrData.variables'''
        for var in NarrData.variables:
            self.move_to_archive(var)

    def remove_grib_file(self):
        '''removes the grib file'''
        logger = logging.getLogger(__name__)
        logger.debug('ExternalFile(Exists:{0}, Name:{1})'
                     .format(os.path.exists(self.get_external_filename()),
                             self.get_external_filename()))
        if os.path.exists(self.get_external_filename()):
            os.unlink(self.get_external_filename())

    def get_next(self, time_increment=timedelta(hours=3)):
        '''returns the next NarrData object'''
        next_date = self.dt + time_increment
        return NarrData(year=next_date.year, month=next_date.month,
                        day=next_date.day, hour=next_date.hour)

    def process_grib_for_variable(self, variable, verbose=False):
        '''Extract the specified variable from the grib file and archive it.

        Precondition:
            A grib file, with the name get_external_filename(), exists in
                current working directory.
            wgrib must be installed on the system
        Postcondition:
            A grib and header for variable will exist in current working
                directory with the name given by get_internal_filename()
        '''
        logger = logging.getLogger(__name__)

        grib_file = self.get_external_filename()
        hdr_name = self.get_internal_filename(variable, 'hdr')
        grb_name = self.get_internal_filename(variable, 'grb')

        if os.path.isfile(grb_name) and os.path.isfile(hdr_name):
            logger.warning('{0} and {1} already exist. Skipping extraction.'
                           .format(hdr_name, grb_name))
            return
        logger.info("Processing [{0}]".format(grib_file))

        # Create inventory/header file to extract the variable data
        cmd_create_temp_header = ['wgrib', grib_file, '|', 'grep', variable,
                                  '>', hdr_name]
        # Create grib files for each variable
        cmd_create_final_grib = ['cat', hdr_name, '|',
                                 'wgrib', grib_file, '-i', '-grib',
                                 '-o', grb_name]
        # Create new inventory/header file for the variable
        cmd_create_final_header = ['wgrib', grb_name, '|', 'grep', variable,
                                   '>', hdr_name]

        cmds = [cmd_create_temp_header, cmd_create_final_grib,
                cmd_create_final_header]

        for cmd_list in cmds:
            cmd = ' '.join(cmd_list)
            output = ''
            logger.info('Executing [{0}]'.format(cmd))
            output = System.execute_cmd(cmd)
            if verbose:
                if len(output) > 0:
                    logger.info(output)

    def move_to_archive(self, variable):
        '''Moves grb and hdr files to archive location.

        Precondition:
            Header and Grib files for variable exist in current directory
        Postcondition:
            Header and Grib files for variable exist in archive directory
            Header and Grib files for variable don't exist in current directory
        '''
        logger = logging.getLogger(__name__)

        dest_path = self.get_internal_drectory()  # Determine the directory
        hdr_name = self.get_internal_filename(variable, 'hdr')
        grb_name = self.get_internal_filename(variable, 'grb')

        System.create_directory(dest_path)  # create it if it does not exist

        # Archive the files
        logger.info('Archiving into [{0}]'.format(dest_path))
        # GRIB
        dest_file = os.path.join(dest_path, grb_name)
        shutil.copyfile(grb_name, dest_file)
        # HEADER
        dest_file = os.path.join(dest_path, hdr_name)
        shutil.copyfile(hdr_name, dest_file)

        # Cleanup the working directory
        if os.path.exists(grb_name):
            os.unlink(grb_name)
        if os.path.exists(hdr_name):
            os.unlink(hdr_name)


class NarrArchive(object):
    '''TODO TODO TODO'''
    _base_aux_dir = None

    @classmethod
    def get_arch_filename(cls, variable, year, month, day, hour, ext):
        '''TODO TODO TODO'''
        return (Config.get('archive_name_format')
                .format(variable, year, month, day, hour*100, ext))

    @classmethod
    def get_arch_dir(cls, year, month, day):
        '''TODO TODO TODO'''
        return (Config.get('archive_directory_format')
                .format(cls.get_base_aux_dir(), year, month, day))

    @classmethod
    def get_base_aux_dir(cls):
        '''TODO TODO TODO'''
        if cls._base_aux_dir is None:  # Check if its not already stored
            cls._base_aux_dir = os.environ.get('LST_AUX_DIR')

            # print("$LST_AUX_DIR="+str(base_aux_dir))
            if cls._base_aux_dir is None:
                Exception('Missing environment variable LST_AUX_DIR')
            if not os.path.isdir(cls._base_aux_dir):
                Exception('LST_AUX_DIR directory does not exist')

        return cls._base_aux_dir


def update(data_to_be_updated):
    '''Downloads, extracts vars, and cleans temp files for data passed in

    Precondition:
        data_to_be_updated is a list of NarrData objects
        External files exist for every data item
    Postcondition:
        Header and Grib files for each variable for each item in
            data_to_be_updated exist in archive directory
        No temporary files exist in the working directory
    '''
    for data in data_to_be_updated:
        try:
            data.get_grib_file()
            data.extract_vars_from_grib()
            data.move_files_to_archive()
        finally:
            data.remove_grib_file()


def report(data_to_report):
    '''Provides measured time, internal mtime and external mtime of data
       passed in

    Note:
        Reports number of files to be downloaded
        Includes header to describe data being output.
        Reports [measured time, internal mtime, external mtime] as csv
    '''
    # Statements helpful for debugging
    logger = logging.getLogger(__name__)
    logger.debug('\n'.join(Ncep.get_list_of_external_data()))
    logger.debug(Ncep.get_dict_of_date_modified())

    report_msg = []
    report_msg.append('Measured, UpdatedLocally, UpdatedOnline')  # Header

    for data in data_to_report:
        line = []
        line.append(data.dt.isoformat())  # Measured datetime

        try:
            line.append(data.get_internal_last_modified().isoformat())
        except NarrData.FileMissing:
            line.append('-')

        try:
            line.append(data.get_external_last_modified().isoformat())
        except NarrData.FileMissing:
            line.append('-')

        report_msg.append(', '.join(line))

    return '\n'.join(report_msg)


def report_between_dates(start_date, end_date):
    '''TODO TODO TODO'''
    data = NarrData.get_next_narr_data_gen(start_date, end_date)
    return report(list(data))


def YYYYMMDD_date(datestring):
    '''TODO TODO TODO'''
    try:
        return datetime.strptime(datestring, '%Y%m%d').date()
    except ValueError:
        logger = logging.getLogger(__name__)
        logger.error('Dates must be the in the format: "YYYYMMDD"')
        raise


def parse_arguments():
    '''TODO TODO TODO'''

    # Create a command line arugment parser
    description = ('Downloads LST auxillary inputs, then archives them for'
                   ' future use. Dates must be the in the format: "YYYYMMDD"')
    parser = ArgumentParser(description=description,
                            formatter_class=ArgumentDefaultsHelpFormatter)

    # ---- Add parameters ----
    parser.add_argument('--start-date',
                        action='store', dest='start_date',
                        metavar='YYYYMMDD', type=YYYYMMDD_date,
                        required=False,
                        default=date.today()-timedelta(days=10),
                        help='The start date of the date range of auxiliary'
                             ' data to download.')

    parser.add_argument('--end-date',
                        action='store', dest='end_date',
                        metavar='YYYYMMDD', type=YYYYMMDD_date,
                        required=False, default=date.today(),
                        help='The end date of the date range of auxiliary'
                             ' data to download.')

    parser.add_argument('--date',
                        action='store', dest='date',
                        metavar='YYYYMMDD', type=YYYYMMDD_date,
                        required=False,
                        help='Sets both start and end date to this date.'
                             ' Overrides start-date and end-date arguments.')

    parser.add_argument('--debug',
                        action='store_true', dest='debug',
                        default=False,
                        help='Turn debug logging on.')

    parser.add_argument('--version',
                        action='version',
                        version='%(prog)s 0.0.1',
                        help='Displays the version of the software.')

    # Parse the command line parameters
    args = parser.parse_args()

    # Check if date was specified. If so then override start and end.
    if args.date is not None:
        args.start_date = args.date
        args.end_date = args.date

    return args


def main(start_date, end_date):
    '''Ensures all data between start_date and end_date are up to date.

    Precondition:
        start_date and end_date are of type datetime.datetime
        start_date and end_date can also be of type datetime.date
    '''
    logger = logging.getLogger(__name__)

    # Determine the data that exists within the date range
    data = NarrData.get_next_narr_data_gen(start_date, end_date)

    # Determine which files are stale or missing internally.
    data_to_be_updated = filter(lambda x: x.need_to_update(), data)
    logger.info('Will download {0} files'.format(len(data_to_be_updated)))
    update(data_to_be_updated)


if __name__ == '__main__':
    cmd_args = parse_arguments()

    log_level = logging.INFO
    if cmd_args.debug:
        log_level = logging.DEBUG

    # Setup the default logger format and level. log to STDOUT
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=log_level,
                        stream=sys.stdout)

    # Turn down the requests and urllib3 logging
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    main(cmd_args.start_date, cmd_args.end_date)
