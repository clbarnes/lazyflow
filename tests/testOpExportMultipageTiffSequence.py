from builtins import object
###############################################################################
#   lazyflow: data flow based lazy parallel computation framework
#
#       Copyright (C) 2011-2014, the ilastik developers
#                                <team@ilastik.org>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the Lesser GNU General Public License
# as published by the Free Software Foundation; either version 2.1
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# See the files LICENSE.lgpl2 and LICENSE.lgpl3 for full text of the
# GNU Lesser General Public License version 2.1 and 3 respectively.
# This information is also available on the ilastik web site at:
#		   http://ilastik.org/license/
###############################################################################
import os
import glob
import shutil
import tempfile

import numpy
import vigra
import h5py

import lazyflow.graph
from lazyflow.operators.opReorderAxes import OpReorderAxes
from lazyflow.operators import OpBlockedArrayCache
from lazyflow.operators.ioOperators import OpExportMultipageTiffSequence, OpStackLoader
from lazyflow.operators.ioOperators.opTiffSequenceReader import OpTiffSequenceReader

import sys
import logging
logger = logging.getLogger('tests.testOpExportMultipageTiffSequence')

class TestOpExportMultipageTiffSequence(object):

    def setUp(self):
        self.graph = lazyflow.graph.Graph()
        self._tmpdir = tempfile.mkdtemp()
        self._name_pattern = 'test_stack_slice_{slice_index}.tiff'
        self._stack_filepattern = os.path.join( self._tmpdir, self._name_pattern )

        # Generate some test data
        self.dataShape = (5, 10, 64, 128, 2)
        self._axisorder = 'tzyxc'
        self.testData = vigra.VigraArray( self.dataShape,
                                         axistags=vigra.defaultAxistags(self._axisorder),
                                         order='C' ).astype(numpy.uint8)
        self.testData[...] = numpy.indices(self.dataShape).sum(0)

    def tearDown(self):
        # Clean up
        shutil.rmtree(self._tmpdir)
        
    def test_Writer(self):
        opData = OpBlockedArrayCache( graph=self.graph )
        opData.BlockShape.setValue( self.testData.shape )
        opData.Input.setValue( self.testData )
        
        opExport = OpExportMultipageTiffSequence(graph=self.graph)
        opExport.FilepathPattern.setValue( self._stack_filepattern )
        opExport.Input.connect( opData.Output )
        opExport.SliceIndexOffset.setValue(22)

        # Run the export
        opExport.run_export()

        globstring = self._stack_filepattern.format( slice_index=999 )
        globstring = globstring.replace('999', '*')

        opReader = OpTiffSequenceReader( graph=self.graph )
        try:
            opReader.GlobString.setValue( globstring )
    
            # (The OpStackLoader produces txyzc order.)
            opReorderAxes = OpReorderAxes( graph=self.graph )
            try:
                opReorderAxes.AxisOrder.setValue( self._axisorder )
                opReorderAxes.Input.connect( opReader.Output )
                
                readData = opReorderAxes.Output[:].wait()
                logger.debug("Expected shape={}".format( self.testData.shape ) )
                logger.debug("Read shape={}".format( readData.shape ) )
                
                assert opReorderAxes.Output.meta.shape == self.testData.shape, "Exported files were of the wrong shape or number."
                assert (opReorderAxes.Output[:].wait() == self.testData.view( numpy.ndarray )).all(), "Exported data was not correct"
            finally:
                opReorderAxes.cleanUp()
        finally:
            opReader.cleanUp()

if __name__ == "__main__":
    # Run this file independently to see debug output.
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stdout))

    ioOpLogger = logging.getLogger('lazyflow.operators.ioOperators')
    ioOpLogger.addHandler( logging.StreamHandler(sys.stdout) )
    ioOpLogger.setLevel(logging.DEBUG)

    import sys
    import nose
    sys.argv.append("--nocapture")    # Don't steal stdout.  Show it on the console as usual.
    sys.argv.append("--nologcapture") # Don't set the logging level to DEBUG.  Leave it alone.
    nose.run(defaultTest=__file__)
