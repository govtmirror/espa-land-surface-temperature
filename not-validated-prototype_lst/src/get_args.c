
#include <string.h>
#include <stdarg.h>
#include <math.h>
#include <getopt.h>


#include "const.h"
#include "utilities.h"
#include "input.h"


/*****************************************************************************
  NAME:  usage

  PURPOSE:  Prints the usage information for this application.

  RETURN VALUE: Type = None
*****************************************************************************/
void
usage ()
{
    printf ("Landsat Surface Temperature\n");
    printf ("\n");
    printf ("usage: scene_based_lst"
            " --xml=input_xml_filename"
            " [--use-tape6]"
            " [--verbose]"
            " [--debug]\n");

    printf ("\n");
    printf ("where the following parameters are required:\n");
    printf ("    --xml: name of the input XML file\n");
    printf ("\n");
    printf ("where the following parameters are optional:\n");
    printf ("    --use-tape6: use the values from the MODTRAN generated"
            " tape6 file? (default is false)\n");
    printf ("    --verbose: should intermediate messages be printed?"
            " (default is false)\n");
    printf ("    --debug: should debug output be generated?"
            " (default is false)\n");
    printf ("\n");
    printf ("scene_based_lst --help will print the usage statement\n");
    printf ("\n");
    printf ("Example: scene_based_lst"
            " --xml=LE70390032010263EDC00.xml"
            " --verbose\n");
    printf ("Note: The scene_based_lst must run from the directory"
            " where the input data are located.\n\n");
}


/*****************************************************************************
  MODULE:  get_args

  PURPOSE:  Gets the command-line arguments and validates that the required
            arguments were specified.

  RETURN VALUE: Type = int
    Value           Description
    -----           -----------
    FAILURE         Error getting the command-line arguments or a command-line
                    argument and associated value were not specified
    SUCCESS         No errors encountered

  NOTES:
    1. Memory is allocated for the input and output files.  All of these
       should be character pointers set to NULL on input.  The caller is
       responsible for freeing the allocated memory upon successful return.
*****************************************************************************/
int get_args
(
    int argc,           /* I: number of cmd-line args */
    char *argv[],       /* I: string of cmd-line args */
    char *xml_filename, /* I: address of input XML metadata filename  */
    bool *use_tape6,    /* O: use the tape6 output */
    bool *verbose,      /* O: verbose flag */
    bool *debug         /* O: debug flag */
)
{
    int c;                         /* current argument index */
    int option_index;              /* index for the command-line option */
    static int verbose_flag = 0;   /* verbose flag */
    static int debug_flag = 0;     /* debug flag */
    static int use_tape6_flag = 0; /* use the results from the tape6 output */
    char errmsg[MAX_STR_LEN];      /* error message */
    char FUNC_NAME[] = "get_args"; /* function name */
    static struct option long_options[] = {
        {"verbose", no_argument, &verbose_flag, 1},
        {"debug", no_argument, &debug_flag, 1},
        {"use-tape6", no_argument, &use_tape6_flag, 1},
        {"xml", required_argument, 0, 'i'},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}
    };

    /* Loop through all the cmd-line options */
    opterr = 0; /* turn off getopt_long error msgs as we'll print our own */
    while (1)
    {
        /* optstring in call to getopt_long is empty since we will only
           support the long options */
        c = getopt_long (argc, argv, "", long_options, &option_index);
        if (c == -1)
        {                       /* Out of cmd-line options */
            break;
        }

        switch (c)
        {
            case 0:
                /* If this option set a flag, do nothing else now. */
                if (long_options[option_index].flag != 0)
                    break;

            case 'h':              /* help */
                usage ();
                return FAILURE;
                break;

            case 'i':              /* xml infile */
                snprintf(xml_filename, PATH_MAX, "%s", optarg);
                break;

            case '?':
            default:
                sprintf (errmsg, "Unknown option %s", argv[optind - 1]);
                usage ();
                RETURN_ERROR (errmsg, FUNC_NAME, FAILURE);
                break;
        }
    }

    /* Make sure the infile was specified */
    if (strlen(xml_filename) <= 0)
    {
        usage ();
        RETURN_ERROR ("XML input file is a required argument", FUNC_NAME,
                      FAILURE);
    }

    /* Set the use_tape6 flag */
    if (use_tape6_flag)
        *use_tape6 = true;
    else
        *use_tape6 = false;

    /* Set the verbose flag */
    if (verbose_flag)
        *verbose = true;
    else
        *verbose = false;

    if (*verbose)
    {
        printf ("XML_input_file = %s\n", xml_filename);
    }

    /* Set the debug flag */
    if (debug_flag)
        *debug = true;
    else
        *debug = false;

    return SUCCESS;
}
