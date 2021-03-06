
# Python distribution modules
from collections import OrderedDict

# Community modules
import numpy as np
from   numpy.linalg     import norm, lstsq
from   matplotlib.dates import datestr2num, num2date
import matplotlib.pyplot as plt

# Local modules

# Global options
np.set_printoptions( precision = 6, suppress = True )

# Python analog of a C++ enumeration using a class
class DistanceMetric :
    Euclidean, Manhatten, Chebyshev = range( 3 )

#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def Prediction( embedding, colNames, target, args ):
    '''
    Simplex projection of observational data (Sugihara, 1990).
    SMap    projection of observational data (Sugihara, 1994).

    The embedding is a matrix of multivariable (column) timeseries
    observatins (rows).  This can be prepared by ReadEmbeddedData() 
    or EmbedData().  target is a vector of observations specified with
    the -r option.  If None, the first data column (j=1) is used.
    Embedding defaults to x(t)+τ; -f (--forwardTau) returns x(t)-τ.

    The embedding is subsetted into two matrices as specified
    by the -l (--library) and -p (--prediction) start:stop indices 
    corresponding to matrix row start:stop (observation) indices.

    FindNeighbors() returns a matrix (neighbors) of row indices in the 
    library matrix. Each neighbors row represents one prediction vector,
    columns the indices of the k_NN nearest neighbors for the 
    prediction vector (phase-space point) in the library matrix.

    SimplexProjection() uses the prediction point neighbors in the 
    library to project the phase-space trajectory for a given point. 
    Prediction() will set k_NN = E + 1 if k_NN not specified.

    SMapProjection(): Sequential Locally Weighted Global Linear Maps
    are constructed from all available neighbors (not just nearest 
    neighbors forming a minimal simplex). The weighting represents an
    exponential decay in neighbor distance with the localization parameter 
    θ (w = exp[-θ d/D]) either creating a global linear map (θ = 0, w = 1)
    or increasingly localized neighbors according to θ.  

    If SMap, Prediction() will set k_NN to all neighbors if k_NN not specified.
    If k_NN specified, it must be > E + 1. 

    Output data are optionally plotted and written to a .csv file. 

    Note: If args.Tp > 0, then the Tp leading rows of the output
    prediction data will be nan. The predictions will be appropriately
    shifted in time, and continue to the end of the prediction library
    (-p) plus args.Tp points.  The Time axis will be extended to account
    for this, and the Observations will have Tp nan's beyond the library 
    time points. 

    --
    Sugihara G. and May R. Nonlinear forecasting as a way of distinguishing 
    chaos from measurement error in time series. Nature, 344:734–741, 1990.

    Sugihara G.. Nonlinear forecasting for the classification of natural 
    time series. Philosophical Transactions: Physical Sciences and 
    Engineering, 348 (1688) : 477–495, 1994.
    '''
    
    #-------------------------------------------------------------
    # Subset library and prediction matrices from embedding matrix
    # args.prediction & args.library indices have been zero-offest
    #-------------------------------------------------------------
    libraryMatrix    = embedding[args.library   [0]:args.library   [-1]:1, ]
    predictionMatrix = embedding[args.prediction[0]:args.prediction[-1]:1, ]

    Time = predictionMatrix[ :, 0 ] # Required to be first (j=0) column

    #--------------------------------------------------------------------
    # Get target vector library subset and Observations prediction subset
    #--------------------------------------------------------------------
    if target is None :
        # default to the j=1 first embedding column
        Observations = embedding[ args.prediction[0]:args.prediction[-1]:1, 1 ]
        target       = embedding[ args.library[0]   :args.library[-1]   :1, 1 ]
    else :
        Observations = target[ args.prediction[0]:args.prediction[-1]:1 ]
        target       = target[ args.library[0]   :args.library[-1]   :1 ]

    #----------------------------------------------------------
    # k_NN nearest neighbors
    #----------------------------------------------------------
    # If Simplex and k_NN not specified, set k_NN to E + 1
    # If SMap and k_NN not specified, set k_NN to all neighbors
    if args.k_NN < 0 :
        if "simplex" in args.method.lower():
            args.k_NN = args.E + 1
            print( "Prediction() Set k_NN to E + 1 = " + str( args.k_NN ) +\
                   " for SimplexProjection." )
            
        elif "smap" in args.method.lower():
            args.k_NN = libraryMatrix.shape[0]
            print( "Prediction() Set k_NN = " + str( args.k_NN ) +\
                   " for SMapProjection." )

    neighbors, distances = FindNeighbors( libraryMatrix,
                                          predictionMatrix, args )

    #----------------------------------------------------------
    # Predictions
    #----------------------------------------------------------
    if 'simplex' in args.method.lower():
        if args.verbose :
            print( "Simplex projection on " + str( args.E ) +\
                   " dimensions of " + args.inputFile + " Tp="+str( args.Tp ))
        
        Predictions = SimplexProjection( libraryMatrix, target,
                                         neighbors, distances, args )
    elif 'smap' in args.method.lower():
        if args.verbose :
            print( "S-Map projection on " + str( args.E ) +\
                   " dimensions of " + args.inputFile + " Tp=" +\
                   str( args.Tp ) + " θ=" + str( args.theta ) )
        
        Predictions, Coeff = SMapProjection( libraryMatrix, predictionMatrix,
                                             target, neighbors, distances,
                                             args )
    else :
        raise RuntimeError( "Prediction() Invalid projection method: ",
                            args.method )

    #----------------------------------------------------------
    # Output
    #----------------------------------------------------------
    # If Tp > 0, offset predicted values by Tp to match observation times
    if args.Tp > 0:
        # Extend Time to accomodate the Tp projections
        # Numpy is terrible at providing floating point arange sequences...
        dt = np.round( Time[1] - Time[0], 3 )
        timeExtension = np.arange( start = Time[-1] + dt,
                                   stop  = Time[-1] + (args.Tp + 1) * dt,
                                   step  = dt )
        timeExtension = timeExtension[ 0 : args.Tp ]
        Time = np.append( Time, timeExtension )

        # Extend and shift Predictions to the appropriate time row
        N_pred      = Predictions.size
        forecast    = Predictions[ (N_pred - args.Tp) : N_pred ]
        Predictions = np.roll( Predictions, args.Tp )
        Predictions = np.append( Predictions, forecast )
        Predictions[ 0 : args.Tp ] = np.nan # Insert NaN for missing data

        # Extend Observations and insert NaN 
        Observations = np.append( Observations, np.full( args.Tp, np.nan ) )

    # Combine into one matrix, create header and write output
    output = np.stack( ( Time, Observations, Predictions ), axis = -1 )
    header = 'Time,Data,Prediction_t(+{0:d})'.format( args.Tp )
    
    if args.outputFile:
        np.savetxt( args.path + args.outputFile, output, fmt = '%.4f',
                    delimiter = ',', header = header, comments = '' )

    # Estimate correlation coefficient on observed : predicted data
    rho, r, rmse, mae = ComputeError( Observations, Predictions )

    if args.verbose :
        print( ("ρ {0:5.3f}  r {1:5.3f}  RMSE {2:5.3f}  "
               "MAE {3:5.3f}").format( rho, r, rmse, mae ) )
    
    if args.Debug:
        print( '   Time     Data      Prediction' )
        print( output[ 0:10, : ] )

    #----------------------------------------------------------
    if args.plot:
        if 'smap' in args.method.lower() :
            block = False # Plot two separate windows, don't block on first
        else:
            block = True

        if args.plotDate :
            Time = num2date( Time )
        
        #-------------------------------------------------------
        # Plot Observation and Prediction
        fig, ax = plt.subplots( 1, 1, figsize = args.figureSize, dpi = 150 )
        ax.plot( Time, Observations, label = 'Observations',
                 color='blue', linewidth = 2 )
        ax.plot( Time, Predictions,
                 label = 'Predictions_t(+{0:d})'.format( args.Tp ),
                 color='red',  linewidth = 2 )
        ax.legend()
        
        ax.set( xlabel = args.plotXLabel,
                ylabel = args.plotYLabel,
                title  = args.inputFile +\
                         '  E=' + str( args.E  ) +\
                         ' Tp=' + str( args.Tp ) +\
                         r' $\rho$=' + str( round( rho, 3 ) ) )
        plt.show( block = block )

        #-------------------------------------------------------
        # Plot S-Map coefficients
        if 'smap' in args.method.lower() :
            plotColors = [ 'blue', 'green', 'red', 'magenta', 'brown', 'black',
                'darkblue', 'darkgreen', 'darkred', 'olive', 'orange', 'gray' ]
            
            # Note that ax2 is an array of length nrows
            fig2, ax2 = plt.subplots( nrows = args.E + 1, ncols = 1,
                                      sharex = True,
                                      figsize = ( args.figureSize[0],
                                                  args.figureSize[0] ),
                                      dpi = 150 )

            Time_coeff = Time[ 0 : len( Time ) - args.Tp ]
            
            for f in range( args.E + 1 ) :
                ax2[f].plot( Time_coeff , Coeff[ :, f],
                             label = 'S-Map Coefficients_{0:d}'.format(f),
                             linewidth = 2, color = plotColors[f] )
            
                ax2[f].legend()

            ax2[ args.E ].set( xlabel = args.plotXLabel )
            
            ax2[ 0 ].set( ylabel = args.plotYLabel,
                          title  = args.inputFile +\
                                   '  E=' + str( args.E  ) +\
                                   ' Tp=' + str( args.Tp ) +\
                                  r' $\rho$=' + str( round( rho, 3 ) ) )
        plt.show()

    return ( rho, rmse, mae, header, output )

#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def SMapProjection( libraryMatrix, predictMatrix, target,
                    neighbors, distances, args):
    '''
    Each row of neighbors, distances corresponds to one prediction vector.
    S-Map prediction requires k_NN > E + 1, default is all neighbors.
   '''
    
    library_N_row = nRow( libraryMatrix ) # Observation Library subset
    predict_N_row = nRow( predictMatrix ) # Prediction  Library subset
    N_row         = nRow( neighbors )     # Prediction k_NN list
    
    if N_row != nRow( distances ) :
        raise RuntimeError( "SMapProjection() Input row dimension mismatch." )

    min_weight   = 1E-6
    predictions  = np.zeros( N_row )
    coefficients = np.full( ( N_row, args.E + 1 ), np.nan )

    for row in range( N_row ) :
        
        D_avg = np.average( distances[ row, : ] )

        # Compute weight (vector) for each k_NN
        if args.theta > 0 :
            w = np.exp( -args.theta * distances[ row, : ] / D_avg )
        else :
            w = np.ones( args.k_NN )

        A = np.zeros( ( args.k_NN, args.E + 1 ) )
        B = np.zeros( args.k_NN )
        
        for k in range( args.k_NN ) :
            lib_row = neighbors[ row, k ] + args.Tp
            
            if lib_row >= library_N_row:
                if args.warnings:
                    print( "SMapProjection() in row " + str( row ) +\
                           " lib_row " + str( lib_row ) + " exceeds library." )
                # JP: Ignore this neighbor with a nan? There will be no pred.
                # B[k] = np.nan
                # Or, use the neighbor at the 'base' of the trajectory
                B[k] = target[ lib_row - args.Tp ]

            else:
                B[k] = target[ lib_row ]

            for j in range( 1, args.E + 1 ) :
                A[ k, j ] = w[k] * predictMatrix[ row, j ]

            A[ k, 0 ] = w[k]

        B = w * B
        
        # numpy least squares approximation
        C, residual, rank, sv = lstsq( A, B, rcond = None )

        # Prediction is local linear projection
        prediction = C[ 0 ]

        for e in range( 1, args.E + 1 ) :
            prediction = prediction + C[ e ] * predictMatrix[ row, e ]

        predictions [ row ]    = prediction
        coefficients[ row, : ] = C

    if args.Debug:
        print( "SMapProjection() predictions:" )
        print( np.round( predictions[ 0:10 ], 4 ) )

    return ( predictions, coefficients )
    
#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def SimplexProjection( libraryMatrix, target,
                       neighbors, distances, args ) :
    '''
    Each row of neighbors, distances corresponds to one prediction vector.
    If k_NN not specified, k_NN set to E+1 in Prediction().
    '''

    library_N_row = nRow( libraryMatrix ) # Observation Library subset
    N_row         = nRow( neighbors     ) # Prediction k_NN list
    
    if N_row != nRow( distances ) :
        raise RuntimeError( "SimplexProjection() Neighbor row mismatch." )

    min_weight = 1E-6
    N_weight   = nCol( neighbors )
    
    predictions = np.zeros( N_row )
        
    for row in range( N_row ) :

        # Compute weight (vector) for each k_NN
        # Establish the exponential weight reference, the 'distance scale'
        min_distance = np.amin( distances[ row, : ] )

        w = np.full( N_weight, min_distance )

        if min_distance == 0 :
            i_zero = np.where( w == 0 )
            if np.size( i_zero ) :
                w[ i_zero ] = 1
        else :
            w = np.fmax( np.exp( -distances[ row, : ] / min_distance ),
                         min_weight )
            
        w_sum = np.sum( w )
        
        # Prediction vector, one element for each weighted k_NN
        y = np.zeros( args.k_NN )
        
        for k in range( args.k_NN ) :

            lib_row = neighbors[ row, k ] + args.Tp
            
            if lib_row >= library_N_row:
                # The k_NN index + Tp is outside the library domain
                if args.warnings:
                    print( "SimplexProjection() in row " + str( row ) +\
                           " lib_row " + str( lib_row ) + " exceeds library." )
                    
                # JP: Ignore this neighbor?
                # x = 0
                # Or, use the neighbor at the 'base' of the trajectory
                x = target[ lib_row - args.Tp ]

            else :
                # The unlagged library data value in target
                x = target[ lib_row ]

            y[k] = w[k] * x

        # Prediction is average of weighted library projections
        predictions[ row ] = np.sum( y ) / w_sum

    if args.Debug:
        print( "SimplexProjection()" )
        print( np.round( predictions[ 0:10 ], 4 ) )

    return predictions
    
#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def FindNeighbors( libraryMatrix, predictionMatrix, args ) :
    '''
    libraryMatrix, predictionMatrix are row subsets of the timeseries
    emdedding matrix, each matrix has rows:

                [ time, data, data-τ, data-2τ, ... ]

    Note: first column     i=0 are time values/indices
          second column    i=1 unlagged data values
          third... columns i=2,3... delayed data values

    Return a tuple of ( neighbors, distances ). neighbors is a matrix of 
    row indices in the library matrix. Each neighbors row represents one 
    prediction vector. Columns are the indices of k_NN nearest neighbors 
    for the prediction vector (phase-space point) in the library matrix.
    distances is a matrix with the same shape as neighbors holding the 
    corresponding distance vectors in each row.
    '''
    prediction_N_row = nRow( predictionMatrix )
    library_N_row    = nRow( libraryMatrix    )

    if args.Debug :
        print( 'FindNeighbors()  predictionMatrix' )
        print( np.round( predictionMatrix[ 0:5, ], 4 ) )
        print( 'prediction_N_row = ' + str( prediction_N_row ) +\
               '  library_N_row = '  + str( library_N_row ) )

    # Identify degenerate library : prediction points
    timePred = predictionMatrix[ :, 0 ]
    timeLib  = libraryMatrix   [ :, 0 ]
    timeIntersection = np.intersect1d( timePred, timeLib )
    if len( timeIntersection ) :
        if args.verbose or args.warnings:
            print( 'FindNeighbors(): Degenerate library and prediction data.' )
        
    # Matrix to hold libraryMatrix row indices
    # One row for each prediction vector, k_NN columns for each index
    neighbors = np.zeros( (prediction_N_row, args.k_NN), dtype = int )

    # Matrix to hold libraryMatrix k_NN distance values
    # One row for each prediction vector, k_NN columns for each index
    distances = np.zeros( (prediction_N_row, args.k_NN) )

    # For each prediction vector (row in predictionMatrix) find the list
    # of library indices that are within k_NN points
    for pred_row in range( prediction_N_row ) :
        # Exclude the 1st column (j=0) of times
        y = predictionMatrix[ pred_row, 1:args.E+1: ]

        # Vectors to hold the indices and values from each comparison
        k_NN_neighbors = np.zeros( args.k_NN, dtype = int )
        k_NN_distances = np.full ( args.k_NN, 1E30 ) # init with 1E30
        
        for lib_row in range( library_N_row ) :
            # If the library point is degenerate with the prediction,
            # ignore it, implementing leave-one-out cross validation.
            # This is detected by comparing the timestamp. 
            if timeLib[ lib_row ] == timePred[ pred_row ] :
                if args.warnings :
                    print( 'FindNeighbors(): ignoring degenerate lib_row ',
                           str( lib_row ), ' and pred_row ', str( pred_row ) )
                continue
            
            # Find distance between the prediction vector (y)
            # and each of the library vectors
            # Exclude the 1st column (j=0) of Time
            d_i = Distance( libraryMatrix[ lib_row, 1:args.E+1: ], y )

            # If d_i is less than the values in k_NN_distances, add to list
            if d_i < np.amax( k_NN_distances ) :
                max_i = np.argmax( k_NN_distances )
                k_NN_neighbors[ max_i ] = lib_row  # Save the index
                k_NN_distances[ max_i ] = d_i      # Save the value

        if np.amax( k_NN_distances ) > 1E29 :
            raise RuntimeError( "FindNeighbors() Library is too small to " +\
                                "resolve " + str( args.k_NN ) + " k_NN "   +\
                                "neighbors." )
        
        # Check for ties.  JP: haven't found any so far...
        if len( k_NN_neighbors ) != len( np.unique( k_NN_neighbors ) ) :
            raise RuntimeError( "FindNeighbors() Degenerate neighbors" )
        
        neighbors[ pred_row, ] = k_NN_neighbors
        distances[ pred_row, ] = k_NN_distances

    # JP: Filter for max_distance
    # if args.epsilon >= 0 :
    
    if args.Debug :
        print( 'FindNeighbors()  neighbors' )
        print( neighbors[ 0:5, ] )

    return ( neighbors, distances )
    
#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def Distance( p1, p2, metric = DistanceMetric.Euclidean ) :
    '''
    '''
    
    if metric == DistanceMetric.Euclidean :
        return norm( p1 - p2 )

    elif metric == DistanceMetric.Manhattan :
        return norm( p1 - p2, ord = 1 )

    elif metric == DistanceMetric.Chebyshev :
        raise RuntimeError( 'Distance(): Chebyshev metric not implemented.' )
            
    else :
        raise RuntimeError( 'Distance(): Unknown metric.' )

#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def ReadEmbeddedData( args ):
    '''
    Read a .csv formatted time-delay embedding from EmbedData(), 
    or a .csv file that has multiple columns of observational data.
    The first column is required to be the "time" variable. It can be
    a numeric, or an ISO datetime string "YYYY-mm-dd". 

    Check that args.prediction and args.library ranges are available.

    If -c (columns) and -r (target) are empty, assume it's a time delay 
    embedding where -E (+1) specifies the number of dimensions and
    columns to return.  Input data consist of a .csv file formatted as:
       [ Time, Dim_1, Dim_2, ... ] 
    where Dim_1 is observed data, Dim_2 data offset by τ, Dim_3 by 2τ...
    E can be less than the total number of columns in the inputFile. 
    The first E + 1 columns (Time, D1, D2, ... D_E) will be returned.

    If -c columns and -r target are specified, decode whether they are 
    column indices (zero-offset integers) or column header names, and 
    set E to the number of specified columns.

    Return tuple with the data matrix, list of column names and the
    library target vector if specified. 
    '''

    embedding = None
    header    = None
    
    # loadtxt returns an ndarray, reads all columns by default
    try:
        csv_matrix = np.loadtxt( args.path + args.inputFile,
                                 delimiter = ',', skiprows = 1 )
    except ValueError as err:
        if 'could not convert string to float' in str( err ):
            # Try with date conversion on first (j=0) column
            csv_matrix = np.loadtxt( args.path + args.inputFile,
                                     delimiter = ',', skiprows = 1,
                                     converters = { 0 : datestr2num },
                                     encoding = None )
            args.plotDate = True
    except:
        print( "ReadEmbeddedData() np.loadtxt() failed on ", args.inputFile )
        raise

    N_row, N_col = csv_matrix.shape
    
    # Parse the header [ Time, Dim_1, Dim_2, ... ]
    csv_head = ''
    with open( args.path + args.inputFile ) as fob:
        csv_head = fob.readline()

    csv_head = csv_head.split(',')
    csv_head = [ h.strip() for h in csv_head ]

    if 'time' not in csv_head[0].lower() :
        raise RuntimeError( 'ReadEmbeddedData() Time not found in ' +\
                            'first column of ' + args.inputFile )

    # Validate requested range of prediction and library
    if args.prediction[0] < 0 or args.prediction[0] > N_row :
        raise RuntimeError( 'ReadEmbeddedData() Invalid prediction start ' +\
                            ' index: ' + str( args.prediction[0] ) )
    
    if args.library[0] < 0 or args.library[0] > N_row :
        raise RuntimeError( 'ReadEmbeddedData() Invalid library start index: ',
                            str( args.library[0] ) )
    
    if args.prediction[1] < 0 or args.prediction[-1] > N_row :
        raise RuntimeError( 'ReadEmbeddedData() Invalid prediction end index: ',
                            str( args.prediction[-1] ) + ' max=' + str(N_row) )
    
    if args.library[1] < 0 or args.library[-1] > N_row :
        raise RuntimeError( 'ReadEmbeddedData() Invalid library end index: ',
                            str( args.library[-1] ) + ' max=' + str( N_row) )

    target = None  # Default None, Assign library target vector if -r

    if len( args.columns ) == 0 and not args.target :
        # -c (columns) and -r (target) not specified.
        # Assume that args.E specifies the number of dimensions and return
        # the first 0 to args.E + 1 columns from the data
        # Col j = 0 is assumed to be "Time" and j = 1 the unlagged data

        if args.E < 0 :
            raise( RuntimeError( 'ReadEmbeddedData() E not specified.' ) )
        
        E_col = args.E + 1  # +1 for time column

        if N_col < E_col :
            raise( RuntimeError( 'ReadEmbeddedData() Number of columns ' +\
                                 str( N_col ) + ' in ' + args.inputFile  +\
                                 ' is less than the number of specified' +\
                                 ' embedding dimension ' + str( args.E ) ) )

        if args.Debug:
            print( 'ReadEmbeddedData()' )
            print( csv_head[ 0:E_col ] )
            print( np.round( csv_matrix[ range( 5 ), 0:E_col ], 4 ) )

        print( "ReadEmbeddedData() columns selected from E+1: " +\
               str( N_row ) + " rows "  +\
               str( N_col ) + " columns from " + args.inputFile +\
               "  Returning " + str( E_col ) + " columns (E+1)." )

        embedding = csv_matrix[ :, 0:E_col ]
        header    = csv_head  [    0:E_col ]
    
    elif args.columns[0].isdigit() and args.target.isdigit() :
        # -c (columns) and -r (target) specified and the first items are digits
        # Convert string digits to int
        column_i = [ int( x ) for x in args.columns ]
        target_i = int( args.target )

        # Collect all columns but exclude duplicates. Place "Time" in col j=0 
        columns_i = np.unique( [0] + column_i )
        
        args.E = len( column_i )
        
        if args.Debug:
            print( 'ReadEmbeddedData()' )
            print( np.take( csv_head, columns_i ) )
            print( np.round( np.take( np.take( csv_matrix,
                                               range( 5 ), axis = 0 ),
                                      columns_i, axis = 1 ), 4 ) )

        print( "ReadEmbeddedData() columns selected from -c -t indices : " +\
               str( N_row ) + " rows " +\
               str( N_col ) + " columns from " + args.inputFile +\
               "  Returning " + str( args.E + 1 ) + " columns (E+1)." )

        embedding = np.take( csv_matrix, columns_i, 1 )
        header    = np.take( csv_head,   columns_i    )
        if args.target:
            target = np.take( csv_matrix, target_i, 1 )

    elif type( args.columns[0] ) is str and type( args.target ) is str :
        # Column names as strings in columns and target
        # Validate that columns and targets are not digits
        if any( [ x.isdigit() for x in args.columns ] ) :
            raise RuntimeError( 'ReadEmbeddedData() Integer indices found ' +\
                                ' in -c column names.' )

        if args.target.isdigit() :
            raise RuntimeError( 'ReadEmbeddedData() Integer index found ' +\
                                ' in -r target name.' )
        
        # Match the column indices to the strings
        D = { key:value for value, key in enumerate( csv_head ) }

        if args.target not in D :
            raise RuntimeError( 'ReadEmbeddedData() Failed to find target ' +\
                                args.target + ' column in ' + args.inputFile )
        target_i = D[ args.target ]

        column_i = []
        
        for col in args.columns :
            if col not in D :
                raise RuntimeError( 'ReadEmbeddedData() Failed to find column'+\
                                    ' ' + col + ' in ' + args.inputFile )
            column_i.append( D[ col ] )
        
        # Collect all columns but exclude duplicates.  Place "Time" in col j=0
        columns_i = np.unique( [0] + column_i )
        
        args.E = len( column_i )
        
        if args.Debug:
            print( 'ReadEmbeddedData()' )
            print( np.take( csv_head, columns_i ) )
            print( np.round( np.take( np.take( csv_matrix,
                                               range( 5 ), axis = 0 ),
                                      columns_i, axis = 1 ), 4 ) )

        print( "ReadEmbeddedData() columns selected from -c -t names:" +\
               str( N_row ) + " rows " +\
               str( N_col ) + " columns from " + args.inputFile +\
               "  Returning " + str( args.E + 1 ) + " columns (E+1)." )

        embedding = np.take( csv_matrix, columns_i, 1 )
        header    = np.take( csv_head,   columns_i    )
        if args.target:
            target = np.take( csv_matrix, target_i, 1 )

    else :
        raise RuntimeError( 'ReadEmbeddedData() Invalid column indexing.' )

    maxEmbedDim = nCol( embedding ) - 1  # First column is time

    if maxEmbedDim < args.E :
        raise RuntimeError( "ReadEmbeddedData() Number of columns in " +\
                            args.inputFile + " is not sufficient for the" +\
                            " requested dimension " + str( args.E ) )

    return ( embedding, header, target )

#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def EmbedData( args ):
    '''
    Reads args.inputFile assumed to be .csv format with a single header
    line and at least two columns: "time" in column i=0, and data values 
    in args.columns.  Time can be a numeric, or an ISO datetime string 
    "YYYY-mm-dd".  Writes the time-delayed (or time-advanced if -f 
    --forwardTau) embedding to args.outputFile (if specified).

    Returns a tuple with embedded matrix, header list (column names)
    and library target vector.  The target vector will be None if -r 
    (target) is not specified.

    Each vector to be embedded is copied into E-1 columns of a matrix
    starting at column j=1 where E is the embedding dimension.  
    Column j=0 are observation times. To adjust the E-1 columns 
    (j=2...E) to contain observations delayed by nτ (n=1,2...E-1), 
    each column is shifted down by Δi = (j_D - 1)τ where j_D is the jth 
    column corresponding to dimension number D out of E total dimensions. 

    !!! This Δi requires that the data column indices are j=1,2...E
    We use column j=0 for the observation time/index values.

    !!! The saved emdedding will be Δi = (E - 1)τ rows less than the 
    original timeseries, coordinates with missing data are deleted.
    If time delays are used then the top Δi rows are deleted, if forward
    times (-f --forwardTau) are specified, then bottom rows are deleted.

    args 
    -E  E            Max embedding dimension, data will be embedded 1:E
    -u  tau          Time delay (tau) in rows.
    -f  forwardTau   Embed t + tau instead of t - tau.
    -c  columns      Data column name(s) in input file (default to col 1). 
    -i  inputFile    Required input data file.
    -p  outputPath
    -oe outputEmbed  Output file for embedding. 
    '''

    if args.E < 0 :
        raise( RuntimeError( 'EmbedData() E not specified.' ) )
    if not len ( args.columns ) :
        raise RuntimeError( "EmbedData() -c columns required." )

    # loadtxt returns an ndarray, reads all columns by default
    # inputFile assumed to be .csv format with a single header line
    try:
        data = np.loadtxt( args.path + args.inputFile,
                           delimiter = ',', skiprows = 1 )
    except ValueError as err:
        if 'could not convert string to float' in str( err ):
            # Try with date conversion on first (j=0) column
            data = np.loadtxt( args.path + args.inputFile,
                               delimiter = ',', skiprows = 1,
                               converters = { 0 : datestr2num },
                               encoding = None )
            args.plotDate = True
    except:
        print( "EmbedData() np.loadtxt() failed on ", args.inputFile )
        raise

    N_row, N_col = data.shape

    if N_col < 2 :
        raise RuntimeError( "EmbedData() at least 2 columns required." )
    
    print( "EmbedData() Read " + str( N_row ) + " rows " +\
           str( N_col ) + " columns from " + args.inputFile +\
           " Data columns: " + str( args.columns ) )

    # Parse the header [ Time, Dim_1, Dim_2, ... ]
    csv_head = ''
    with open( args.path + args.inputFile ) as fob:
        csv_head = fob.readline()

    csv_head = csv_head.split(',')
    csv_head = [ h.strip() for h in csv_head ]

    # Dictionary of column index : label from inputFile
    D = { key:value for value, key in enumerate( csv_head ) }

    # Get target data vector if requested (-r)
    target = None
    if args.target :
        if args.target not in D.keys() :
            raise RuntimeError( "EmbedData() Failed to find target " +\
                                args.target + " in " + args.inputFile)

        delta_row = (args.E - 1) * args.tau
        if args.forwardTau :
            # Ignore bottom delta_row
            target = data[ 0:(N_row - delta_row), D[ args.target ] ]
        else :
            # Ignore the top delta_row
            target = data[ delta_row:N_row, D[ args.target ] ]
            
    header = ['Time,'] # Output header
    
    # Collection of embedColumn : matrix
    embeddings = OrderedDict() 
    # Note we use an OrderedDict() for embeddings to ensure that the order
    # of data columns in args.columns is the order in which the
    # embeddings are returned.  This is important since Prediction()
    # assumes that the first (j=0) column is 'time' and the second
    # (j=1) column is the prediction variable (data).
    
    # Process each column specified in args.columns
    for embedColumn in args.columns :
        # Zero-offset index to data column
        i_embedColumn = None

        if embedColumn.isdigit():
            i_embedColumn = int( embedColumn )
        else :
            # Find the matching data column name and associated index
            if embedColumn not in D.keys() :
                raise RuntimeError( "EmbedData() Failed to find column " +\
                                    embedColumn + " in " + args.inputFile)
            
            i_embedColumn = D[ embedColumn ]
    
        if i_embedColumn > N_col :
            raise RuntimeError( "EmbedData() embedColumn " + embedColumn +\
                                " (" + str(i_embedColumn) +\
                                ") too large for file " + args.inputFile )

        # Create matrix to hold the original and delayed observations
        m = np.zeros( ( N_row + args.tau - 1, args.E + 1 ) )
    
        # Copy data index/time into column j = 0 and data vector into j=1
        # !!! Need the time in column 0 so the Δi row indexing works
        m[ :, 0 ] = data[ :, 0 ]
        m[ :, 1 ] = data[ :, i_embedColumn ]

        # Copy shifted data into remaining columns
        # The basic slice syntax is [i:j:k] where i is the starting index,
        # j is the stopping index, and k is the step.
        if args.forwardTau :
            # Embed as t + tau
            for j in range( 2, args.E + 1 ) :
                delta_row = ( j - 1 ) * args.tau

                m[ 0 : (N_row - delta_row) : 1, j ] =\
                   data[ delta_row : N_row : 1, i_embedColumn ]
    
            # Delete the Δi = (E - 1)τ bottom rows that have partial data
            # np.s_[] is the slice operator,  axis = 0 : delete row dimension
            del_row = N_row - (args.E - 1) * args.tau
            m = np.delete( m, np.s_[ del_row : N_row : 1 ], 0 )

        else :
            # Embed as t - tau
            for j in range( 2, args.E + 1 ) :
                delta_row = ( j - 1 ) * args.tau

                m[ delta_row : N_row : 1, j ] =\
                   data[ 0 : N_row - delta_row : 1, i_embedColumn ]
    
            # Delete the Δi = (E - 1)τ top rows that have partial data
            # np.s_[] is the slice operator,  axis = 0 : delete row dimension
            del_row = (args.E - 1) * args.tau
            m = np.delete( m, np.s_[ 0 : del_row : 1 ], 0 )

        embeddings[ embedColumn ] = m

    #----------------------------------------------------------
    # Combine the possibly multiple embeddings into one matrix
    first_key = list( embeddings.keys() )[0]
    
    for key in embeddings.keys() :

        mat = embeddings[ key ] # Each embedding matrix has time in j=0
        
        if key == first_key :
            M = mat
        else:
            # Don't append the time column
            M = np.concatenate( ( M, mat[ :, 1:args.E + 1 ] ), axis = 1 )

        # Header
        for tau in range( 0, args.E ) :
            if args.forwardTau :
                header.append( key + '(t+{0:d}),'.format(tau) )
            else:
                header.append( key + '(t-{0:d}),'.format(tau) )

    # Format header list into a string for savetxt 
    # and Header list with the trailing ',' stripped
    header_str = ''.join(header)
    Header     = [ h[0:len(h)-1] for h in header ]

    if args.Debug:
        print( "EmbedData() " + args.inputFile + " E = " + str( args.E ) )
        print( header_str )
        print( M[ 0:5, : ] )
    
    #------------------------------------------------------------------
    # Write output
    if args.outputEmbed:
        np.savetxt( args.path + args.outputEmbed, M, fmt = '%.6f',
                    delimiter = ',', header = header_str, comments = '' )

    return ( M, Header, target )

#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def ComputeError( obs, pred ):
    '''
    '''
    p_not_nan = np.logical_not( np.isnan( pred ) ) # True / False
    o_not_nan = np.logical_not( np.isnan( obs  ) )

    i_not_nan = np.intersect1d( np.where( p_not_nan == True ),
                                np.where( o_not_nan == True ) )

    if len( i_not_nan ) :
        obs  = obs [ i_not_nan ]
        pred = pred[ i_not_nan ]

    N = len( pred )

    sumPred    = np.sum( pred )
    sumObs     = np.sum( obs  )
    sumSqrPred = np.sum( np.power( pred, 2 ) )
    sumSqrObs  = np.sum( np.power( obs,  2 ) )
    sumErr     = np.sum( np.fabs ( obs - pred ) )
    sumSqrErr  = np.sum( np.power( obs - pred, 2 ) )
    sumProd    = np.dot( obs, pred )

    if sumSqrPred * N == sumSqrPred :
        r = 0
    else:
        r = ( ( sumProd * N - sumObs * sumPred ) / \
              np.sqrt( ( sumSqrObs  * N - sumSqrObs  ) * \
                       ( sumSqrPred * N - sumSqrPred ) ) )

    rmse = np.sqrt( sumSqrErr / N )

    mae = sumErr / N

    if sum( pred ) == 0 :
        rho = 0
    else :
        rho = np.corrcoef( obs, pred )[0, 1]

    return ( rho, r, rmse, mae )

#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def nRow( A ) :
    '''
    Convenience function for number of rows since np.shape is clunky
    '''
    s = np.shape( A )
    if ( len( s ) != 2 ) :
        raise RuntimeError( "nRow() numpy object is not a 2-D matrix." )
    
    return A.shape[0]

#----------------------------------------------------------------------------
# 
#----------------------------------------------------------------------------
def nCol( A ) :
    '''
    Convenience function for number of rows since np.shape is clunky
    '''
    s = np.shape( A )
    if ( len( s ) != 2 ) :
        raise RuntimeError( "nCol() numpy object is not a 2-D matrix." )
    
    return A.shape[1]
