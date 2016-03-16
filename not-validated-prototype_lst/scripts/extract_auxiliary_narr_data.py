#! /usr/bin/env python

'''
    FILE: extract_narr_aux_data.py

    PURPOSE: Calls the executables or module routines required to generate LST
             products.

    PROJECT: Land Satellites Data Systems Science Research and Development
             (LSRD) at the USGS EROS

    LICENSE: NASA Open Source Agreement 1.3
'''

import os
import sys
import logging
from argparse import ArgumentParser
from datetime import datetime, timedelta

# Import the metadata api found in the espa-product-formatter project
import metadata_api

# Import local modules
import lst_utilities as util
from lst_environment import Environment


class AuxNARRGribProcessor(object):
    '''
    Description:
        Extracts parameters from the auxillary NARR data in grib format and
        places them into 'parameter' named directories.
    '''

    def __init__(self, xml_filename):
        super(AuxNARRGribProcessor, self).__init__()

        # Keep local copies of these
        self.xml_filename = xml_filename

        self.parms_to_extract = ['HGT', 'SPFH', 'TMP']
        self.aux_path_template = '{0:0>4}/{1:0>2}/{2:0>2}'
        self.aux_name_template = 'NARR_3D.{0}.{1:04}{2:02}{3:02}.{4:04}.{5}'

        self.date_template = '{0:0>4}{1:0>2}{2:0>2}'

        environment = Environment()
        lst_aux_dir = environment.get_lst_aux_directory()

        self.dir_template = lst_aux_dir + '/{0}/{1}'

        self.record_idx = 0
        self.pressure_idx = 6

        # Setup the logger to use
        self.logger = logging.getLogger(__name__)

    def extract_grib_data(self, hdr_path, grb_path, output_dir):
        '''
        Description:
            Configures a command line for calling the wgrib executable and
            then calls it to extract the required information from the grib
            file.

            The output is placed into a specified directory based on the
            input.
        '''

        util.System.create_directory(output_dir)

        with open(hdr_path, 'r') as hdr_fd:
            for line in hdr_fd.readlines():
                self.logger.debug(line.strip())
                parts = line.strip().split(':')
                record = parts[self.record_idx]
                pressure = parts[self.pressure_idx].split('=')[1]
                self.logger.debug('{0} {1}'.format(record, pressure))

                filename = '.'.join([pressure, 'txt'])
                path = os.path.join(output_dir, filename)
                cmd = ['wgrib', grb_path,
                       '-d', record,
                       '-text', '-o', path]
                cmd = ' '.join(cmd)
                self.logger.info('wgrib command = [{0}]'.format(cmd))

                # Extract the pressure data and raise any errors
                output = ''
                try:
                    output = util.System.execute_cmd(cmd)
                except Exception:
                    self.logger.error('Failed to unpack data')
                    raise
                finally:
                    if len(output) > 0:
                        self.logger.info(output)

    def extract_aux_data(self):
        '''
        Description:
            Builds the strings required to locate the auxillary data in the
            archive then extracts the parameters into parameter named
            directories.
        '''

        xml = metadata_api.parse(self.xml_filename, silence=True)
        global_metadata = xml.get_global_metadata()
        acq_date = str(global_metadata.get_acquisition_date())
        scene_center_time = str(global_metadata.get_scene_center_time())

        # Extract the individual parts from the date
        year = int(acq_date[:4])
        month = int(acq_date[5:7])
        day = int(acq_date[8:])

        # Extract the hour parts from the time and convert to an int
        hour = int(scene_center_time[:2])
        self.logger.debug('Using Acq. Date = {0} {1} {2}'
                          .format(year, month, day))
        self.logger.debug('Using Scene Center Hour = {0:0>2}'.format(hour))

        del global_metadata
        del xml

        # Determine the 3hr increments to use from the auxillary data
        # We want the one before and after the scene acquisition time
        # and convert back to formatted strings
        hour_1 = hour - (hour % 3)
        t_delta = timedelta(hours=3)  # allows easy advance to the next day

        date_1 = datetime(year, month, day, hour_1)
        date_2 = date_1 + t_delta
        self.logger.debug('Date 1 = {0}'.format(str(date_1)))
        self.logger.debug('Date 2 = {0}'.format(str(date_2)))

        for parm in self.parms_to_extract:
            # Build the source filenames for date 1
            filename = self.aux_name_template.format(parm,
                                                     date_1.year,
                                                     date_1.month,
                                                     date_1.day,
                                                     date_1.hour * 100,
                                                     'hdr')

            aux_path = (self.aux_path_template.format(date_1.year,
                                                      date_1.month,
                                                      date_1.day))

            hdr_1_path = self.dir_template.format(aux_path, filename)

            grb_1_path = hdr_1_path.replace('.hdr', '.grb')

            self.logger.info('Using {0}'.format(hdr_1_path))
            self.logger.info('Using {0}'.format(grb_1_path))

            # Build the source filenames for date 2
            filename = self.aux_name_template.format(parm,
                                                     date_2.year,
                                                     date_2.month,
                                                     date_2.day,
                                                     date_2.hour * 100,
                                                     'hdr')

            aux_path = (self.aux_path_template.format(date_2.year,
                                                      date_2.month,
                                                      date_2.day))

            hdr_2_path = self.dir_template.format(aux_path, filename)

            grb_2_path = hdr_2_path.replace('.hdr', '.grb')

            self.logger.info('Using {0}'.format(hdr_2_path))
            self.logger.info('Using {0}'.format(grb_2_path))

            # Verify that the files we need exist
            if (not os.path.exists(hdr_1_path) or
                    not os.path.exists(hdr_2_path) or
                    not os.path.exists(grb_1_path) or
                    not os.path.exists(grb_2_path)):
                raise Exception('Required LST AUX files are missing')

            # Date 1
            output_dir = '{0}_1'.format(parm)
            self.extract_grib_data(hdr_1_path, grb_1_path, output_dir)

            # Date 2
            output_dir = '{0}_2'.format(parm)
            self.extract_grib_data(hdr_2_path, grb_2_path, output_dir)


def main():
    '''
    Description:
        Gathers input parameters and extracts auxiliary NARR data.  Calling
        main is intended for debugging pruposes only.
    '''

    # Create a command line arugment parser
    description = ('Retrieves and generates auxillary LST inputs, then'
                   ' processes and calls other executables for LST generation')
    parser = ArgumentParser(description=description)

    # ---- Add parameters ----
    # Required parameters
    parser.add_argument('--xml',
                        action='store', dest='xml_filename',
                        required=False, default=None,
                        help='The XML metadata file to use')

    parser.add_argument('--debug',
                        action='store_true', dest='debug',
                        required=False, default=False,
                        help='Keep any debugging data')

    parser.add_argument('--version',
                        action='store_true', dest='version',
                        required=False, default=False,
                        help='Reports the version of the software')

    # Parse the command line parameters
    args = parser.parse_args()

    # Command line arguments are required so print the help if none were
    # provided
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)  # EXIT FAILURE

    # Report the version and exit
    if args.version:
        print(util.Version.version_text())
        sys.exit(0)  # EXIT SUCCESS

    # Verify that the --xml parameter was specified
    if args.xml_filename is None:
        raise Exception('--xml must be specified on the command line')

    # Verify that the XML filename provided is not an empty string
    if args.xml_filename == '':
        raise Exception('No XML metadata filename provided.')

    # Setup the logging level
    log_level = logging.INFO
    if args.debug:
        log_level = logging.DEBUG

    # Setup the default logger format and level.  Log to STDOUT.
    logging.basicConfig(format=('%(asctime)s.%(msecs)03d %(process)d'
                                ' %(levelname)-8s'
                                ' %(filename)s:%(lineno)d:'
                                '%(funcName)s -- %(message)s'),
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=log_level,
                        stream=sys.stdout)

    # Get the logger
    logger = logging.getLogger(__name__)

    try:
        logger.info('Extracting LST AUX data')
        current_processor = AuxNARRGribProcessor(args.xml_filename)
        current_processor.extract_aux_data()

    except Exception:
        logger.exception('Failed processing auxiliary NARR data')
        raise

    logger.info('Completed extraction of auxiliary NARR data')


if __name__ == '__main__':
    '''
    Description:
        Simply call the main routine for stand alone processing.  This code is
        intended to be imported and the class used.  Calling main is intended
        for debugging pruposes only.
    '''

    try:
        main()
    except Exception:
        sys.exit(1)  # EXIT FAILURE

    sys.exit(0)  # EXIT SUCCESS
