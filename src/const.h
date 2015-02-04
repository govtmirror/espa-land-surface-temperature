#ifndef CONST_H
#define CONST_H


#include <math.h>


#define LST_VERSION "1.0.0"


#define TWO_PI (2.0 * PI)
#define HALF_PI (PI / 2.0)


#define DEG (180.0 / PI)
#define RAD (PI / 180.0)


#ifndef SUCCESS
    #define SUCCESS  0
#endif


#ifndef FAILURE
    #define FAILURE 1
#endif


#define NUM_ELEVATIONS 9
#define NARR_ROW 349
#define NARR_COL 277


#define MINSIGMA 1e-5


#define MAX_STR_LEN 512


/* Provides for the element size of the LST point result records, along with
   the locations of the individual elements.

   Only required because a 2d-array was used instead of a data structure.
*/
typedef enum {
    LST_LATITUDE = 0,
    LST_LONGITUDE,
    LST_HEIGHT,
    LST_TAU,
    LST_UPWELLED_RADIANCE,
    LST_DOWNWELLED_RADIANCE,
    LST_NUM_ELEMENTS
} LST_RESULTS;


#endif
