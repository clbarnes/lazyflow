import numpy, vigra, h5py

from lazyflow.graph import *
import gc
from lazyflow import roi
import copy

from operators import OpArrayPiper, OpMultiArrayPiper

from generic import OpMultiArrayStacker, getSubKeyWithFlags, popFlagsFromTheKey

from threading import Lock


class OpMultiArrayStackerOld(Operator):
    inputSlots = [MultiInputSlot("Images")]
    outputSlots = [OutputSlot("Output")]

    name = "Multi Array Stacker"
    category = "Misc"

    def notifySubConnect(self, slots, indexes):
        dtypeDone = False        
        c = 0
        for inSlot in self.inputs["Images"]:
            if inSlot.partner is not None:
                if dtypeDone is False:
                    self.outputs["Output"]._dtype = inSlot.dtype
                    self.outputs["Output"]._axistags = copy.copy(inSlot.axistags)
                    if self.outputs["Output"]._axistags.axisTypeCount(vigra.AxisType.Channels) == 0:
                        self.outputs["Output"]._axistags.insertChannelAxis()
                    
                if inSlot.axistags.axisTypeCount(vigra.AxisType.Channels) == 0:
                    c += 1
                else:
                    c += inSlot.shape[inSlot.axistags.channelIndex]
        self.outputs["Output"]._shape = inSlot.shape[:-1] + (c,)    

    
    def getOutSlot(self, slot, key, result):
        cnt = 0
        written = 0
        start, stop = roi.sliceToRoi(key, self.outputs["Output"].shape)
        key = key[:-1]
        requests = []
        for i, inSlot in enumerate(self.inputs['Images']):
            if inSlot.partner is not None:
                req = None
                if inSlot.axistags.axisTypeCount(vigra.AxisType.Channels) == 0:
                    #print "########################", inSlot.shape, inSlot.axistags
                    if cnt >= start[-1] and start[-1] + written < stop[-1]:
                        #print "OOOOOOOOOOOOOOOOO1", i, cnt, start[-1], stop[-1], result[..., cnt].shape
                        req = inSlot[key].writeInto(result[..., cnt])
                        written += 1
                    cnt += 1
                    
                else:
                    channels = inSlot.shape[inSlot.axistags.channelIndex]
                    if cnt + channels >= start[-1] and start[-1] - cnt < channels and start[-1] + written < stop[-1]:
                        
                        begin = 0
                        if cnt < start[-1]:
                            begin = start[-1] - cnt
                        end = channels
                        if cnt + end > stop[-1]:
                            end -= cnt + end - stop[-1]
                        key_ = key + (slice(begin,end,None),)

                        #print "OOOOOOOOOOOOOO2", i, cnt, start[-1],stop[-1],inSlot.shape[-1], begin, end, key_, result.shape, result[...,written:written+end-begin].shape, written,written+end-begin
                        assert (end <= numpy.array(inSlot.shape)).all()
                        assert (begin < numpy.array(inSlot.shape)).all(), "begin : %r, shape: %r" % (begin, inSlot.shape)
                        req = inSlot[key_].writeInto(result[...,written:written+end-begin])
                        written += end - begin
                    cnt += channels
               
                if req is not None:
                   requests.append(req)
        
        for r in requests:
            r.wait()


class Op5ToMulti(Operator):
    name = "5 Elements to Multislot"
    category = "Misc"

    
    inputSlots = [InputSlot("Input0"),InputSlot("Input1"),InputSlot("Input2"),InputSlot("Input3"),InputSlot("Input4")]
    outputSlots = [MultiOutputSlot("Outputs")]
        
    def notifyConnect(self, slot):
        length = 0
        for slot in self.inputs.values():
            if slot.connected():
                length += 1                

        self.outputs["Outputs"].resize(length)

        i = 0
        for sname in sorted(self.inputs.keys()):
            slot = self.inputs[sname]
            if slot.connected():
                self.outputs["Outputs"][i]._dtype = slot.dtype
                self.outputs["Outputs"][i]._axistags = copy.copy(slot.axistags)
                self.outputs["Outputs"][i]._shape = slot.shape
                i += 1       

    def notifyDisonnect(self, slot):
        self.notifyConnect(None)                        
        
    def getSubOutSlot(self, slots, indexes, key, result):
        i = 0
        for sname in sorted(self.inputs.keys()):
            slot = self.inputs[sname]
            if slot.connected():
                if i == indexes[0]:
                    result[:] = slot[key].allocate().wait()
                    break
                i += 1                

class Op10ToMulti(Op5ToMulti):
    name = "10 Elements to Multislot"
    category = "Misc"

    inputSlots = [InputSlot("Input0"), InputSlot("Input1"),InputSlot("Input2"),InputSlot("Input3"),InputSlot("Input4"),InputSlot("Input5"), InputSlot("Input6"),InputSlot("Input7"),InputSlot("Input8"),InputSlot("Input9")]
    outputSlots = [MultiOutputSlot("Outputs")]


class Op20ToMulti(Op5ToMulti):
    name = "20 Elements to Multislot"
    category = "Misc"

    inputSlots = [InputSlot("Input00"), InputSlot("Input01"),InputSlot("Input02"),InputSlot("Input03"),InputSlot("Input04"),InputSlot("Input05"), InputSlot("Input06"),InputSlot("Input07"),InputSlot("Input08"),InputSlot("Input09"),InputSlot("Input10"), InputSlot("Input11"),InputSlot("Input12"),InputSlot("Input13"),InputSlot("Input14"),InputSlot("Input15"), InputSlot("Input16"),InputSlot("Input17"),InputSlot("Input18"),InputSlot("Input19")]
    outputSlots = [MultiOutputSlot("Outputs")]



class OpNToMulti(Op5ToMulti):
    
    name = "N Elements to Multislot"
    category = "Misc"

    
    outputSlots = [MultiOutputSlot("Outputs")]

    
    def __init__(self,g,N=20):
        self.inputSlots = []
        for i in range(N):
            self.inputSlots.append(InputSlot("Input"+str(i)))
        
                
        Op5ToMulti.__init__(self,g)




class OpPixelFeatures(OperatorGroup):
    name="OpPixelFeatures"
    category = "Vigra filter"
    
    inputSlots = [InputSlot("Input"), InputSlot("Matrix"), InputSlot("Scales")]
    outputSlots = [OutputSlot("Output"), OutputSlot("ArrayOfOperators")]
    
    def _createInnerOperators(self):
        # this method must setup the
        # inner operators and connect them (internally)
        
        self.source = OpArrayPiper(self.graph)
        
        self.stacker = OpMultiArrayStacker(self.graph)
        
        self.multi = Op20ToMulti(self.graph)
        
        
        self.stacker.inputs["Images"].connect(self.multi.outputs["Outputs"])
        
        
    def notifyConnectAll(self):
        if self.inputs["Scales"].connected() and self.inputs["Matrix"].connected():

            self.stacker.inputs["Images"].disconnect()
            self.scales = self.inputs["Scales"].value
            self.matrix = self.inputs["Matrix"].value 
            
            if type(self.matrix)!=numpy.ndarray:
              print "Please input a numpy ndarray"
              raise
            
            dimCol = len(self.scales)
            dimRow = self.matrix.shape[0]
            
            assert dimCol== self.matrix.shape[1], "Please check the matrix or the scales they are not the same"
            assert dimRow==4, "Right now the features are fixed"
    
            oparray = []
            for j in range(dimCol):
                oparray.append([])
    
            i = 0
            for j in range(dimCol):
                oparray[i].append(OpGaussianSmoothing(self.graph))
                oparray[i][j].inputs["Input"].connect(self.source.outputs["Output"])
                oparray[i][j].inputs["sigma"].setValue(self.scales[j])
            i = 1
            for j in range(dimCol):
                oparray[i].append(OpLaplacianOfGaussian(self.graph))
                oparray[i][j].inputs["Input"].connect(self.source.outputs["Output"])
                oparray[i][j].inputs["scale"].setValue(self.scales[j])
            i = 2
            for j in range(dimCol):
                oparray[i].append(OpHessianOfGaussian(self.graph))
                oparray[i][j].inputs["Input"].connect(self.source.outputs["Output"])
                oparray[i][j].inputs["sigma"].setValue(self.scales[j])
            i = 3
            for j in range(dimCol):   
                oparray[i].append(OpHessianOfGaussianEigenvalues(self.graph))
                oparray[i][j].inputs["Input"].connect(self.source.outputs["Output"])
                oparray[i][j].inputs["scale"].setValue(self.scales[j])
            
            self.outputs["ArrayOfOperators"][0] = oparray
            
            #disconnecting all Operators
            for i in range(dimRow):
                for j in range(dimCol):
                    #print "Disconnect", (i*dimRow+j)
                    self.multi.inputs["Input%02d" %(i*dimRow+j)].disconnect() 
            
            #connect individual operators
            for i in range(dimRow):
                for j in range(dimCol):
                    val=self.matrix[i,j]
                    if val:
                        #print "Connect", (i*dimRow+j)
                        self.multi.inputs["Input%02d" %(i*dimRow+j)].connect(oparray[i][j].outputs["Output"])
            
            #additional connection with FakeOperator
            if (self.matrix==0).all():
                fakeOp = OpGaussianSmoothing(self.graph)
                fakeOp.inputs["Input"].connect(self.source.outputs["Output"])
                fakeOp.inputs["sigma"].setValue(10)
                self.multi.inputs["Input%02d" %(i*dimRow+j+1)].connect(fakeOp.outputs["Output"])
                self.multi.inputs["Input%02d" %(i*dimRow+j+1)].disconnect() 
                self.stacker.outputs["Output"].shape=()
                return
         
            
            index = len(self.source.outputs["Output"].shape) - 1
            self.stacker.inputs["AxisFlag"].setValue('c')
            self.stacker.inputs["AxisIndex"].setValue(index)
            self.stacker.inputs["Images"].connect(self.multi.outputs["Outputs"])
            
    
    def getInnerInputs(self):
        inputs = {}
        inputs["Input"] = self.source.inputs["Input"]
        return inputs
        
    def getInnerOutputs(self):
        outputs = {}
        outputs["Output"] = self.stacker.outputs["Output"]
        return outputs


def getAllExceptAxis(ndim,index,slicer):
    res= [slice(None, None, None)] * ndim
    res[index] = slicer
    return tuple(res)

class OpBaseVigraFilter(OpArrayPiper):
    inputSlots = [InputSlot("Input"), InputSlot("sigma", stype = "float")]
    outputSlots = [OutputSlot("Output")]    
    
    name = "OpBaseVigraFilter"
    category = "Vigra filter"
    
    vigraFilter = None
    outputDtype = numpy.float32 
    inputDtype = numpy.float32
    supportsOut = True
    
    def __init__(self, graph, register = True):
        OpArrayPiper.__init__(self, graph, register = register)
        self.supportsOut = False
        
    def getOutSlot(self, slot, key, result):
        
        kwparams = {}        
        for islot in self.inputs.values():
            if islot.name != "Input":
                kwparams[islot.name] = islot.value
        
        if self.inputs.has_key("sigma"):
            sigma = self.inputs["sigma"].value
        elif self.inputs.has_key("scale"):
            sigma = self.inputs["scale"].value
        elif self.inputs.has_key("sigma1"):
            sigma = self.inputs["sigma1"].value
        elif self.inputs.has_key("innerScale"):
            sigma = self.inputs["innerScale"].value
            
        largestSigma = sigma*3.5 #ensure enough context for the vigra operators
                
        shape = self.outputs["Output"].shape
        
        axistags = self.inputs["Input"].axistags
        #print "DUDE, " , axistags
        
        channelAxis=self.inputs["Input"].axistags.index('c')
        hasTimeAxis = self.inputs["Input"].axistags.axisTypeCount(vigra.AxisType.Time)
        timeAxis=self.inputs["Input"].axistags.index('t')
        subkey = popFlagsFromTheKey(key,axistags,'c')
        subshape=popFlagsFromTheKey(shape,axistags,'c')
        
        
        oldstart, oldstop = roi.sliceToRoi(key, shape)
        
        start, stop = roi.sliceToRoi(subkey,subkey)
        newStart, newStop = roi.extendSlice(start, stop, subshape, largestSigma)
        readKey = roi.roiToSlice(newStart, newStop)
        
        
        writeNewStart = start - newStart
        writeNewStop = writeNewStart +  stop - start
        
        if (writeNewStart == 0).all() and (newStop == writeNewStop).all():
            fullResult = True
        else:
            fullResult = False
        
        writeKey = roi.roiToSlice(writeNewStart, writeNewStop)
        writeKey = list(writeKey)
        writeKey.insert(channelAxis, slice(None,None,None))
        writeKey = tuple(writeKey)         
        
        writeKey= popFlagsFromTheKey(writeKey,axistags,'t')
        
        channelsPerChannel = self.resultingChannels()
        
        
        
        i2 = 0          
        for i in range(int(numpy.floor(1.0 * oldstart[channelAxis]/channelsPerChannel)),int(numpy.ceil(1.0 * oldstop[channelAxis]/channelsPerChannel))):
            
            treadKey=list(readKey)
            treadKey.insert(channelAxis, slice(i,i+1,None))
            treadKey=tuple(treadKey)
            #print readKey,'iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii'
            #print treadKey, "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"
            req = self.inputs["Input"][treadKey].allocate()
            t = req.wait()
            
            t = numpy.require(t, dtype=self.inputDtype)
            
            t = t.view(vigra.VigraArray)
            t.axistags = copy.copy(axistags)
            t = t.insertChannelAxis()
            

            sourceBegin = 0
            if oldstart[channelAxis] > i * channelsPerChannel:
                sourceBegin = oldstart[channelAxis] - i * channelsPerChannel
            sourceEnd = channelsPerChannel
            if oldstop[channelAxis] < (i+1) * channelsPerChannel:
                sourceEnd = channelsPerChannel - ((i+1) * channelsPerChannel - oldstop[channelAxis])
            
            destBegin = i2
            destEnd = i2 + sourceEnd - sourceBegin
            
            if channelsPerChannel>1:
                tkey=getAllExceptAxis(len(shape),channelAxis,slice(destBegin,destEnd,None))                   
                resultArea = result[tkey]
            else:
                tkey=getAllExceptAxis(len(shape),channelAxis,slice(i2,i2+1,None)) 
                resultArea = result[tkey]

            
            for step,image in enumerate(t.timeIter()):
                #print writeKey, 'EEEEEEEEEEEEEEEEEEEEEEEEE'
                temp = self.vigraFilter(image, **kwparams)
                #print type(temp), temp.axistags, temp.shape
                temp=temp[writeKey]
                nChannelAxis = channelAxis - 1
                if timeAxis > channelAxis:
                    nChannelAxis = channelAxis 
                twriteKey=getAllExceptAxis(temp.ndim, nChannelAxis, slice(sourceBegin,sourceEnd,None))
                
                if hasTimeAxis > 0:
                    tresKey  = getAllExceptAxis(temp.ndim, timeAxis, step)
                else:
                    tresKey  = slice(None, None,None)
                
                #print tresKey, twriteKey, resultArea.shape, temp.shape
                
                resultArea[tresKey] = temp[twriteKey]
                 
                
            i2 += channelsPerChannel

            
    def notifyConnectAll(self):
        numChannels  = 1
        inputSlot = self.inputs["Input"]
        if inputSlot.axistags.axisTypeCount(vigra.AxisType.Channels) > 0:
            channelIndex = self.inputs["Input"].axistags.channelIndex
            numChannels = self.inputs["Input"].shape[channelIndex]
            inShapeWithoutChannels = inputSlot.shape[:-1]
        else:
            inShapeWithoutChannels = inputSlot.shape
                    
        self.outputs["Output"]._dtype = self.outputDtype
        p = self.inputs["Input"].partner
        self.outputs["Output"]._axistags = copy.copy(inputSlot.axistags)
        
        channelsPerChannel = self.resultingChannels()
        self.outputs["Output"]._shape = inShapeWithoutChannels + (numChannels * channelsPerChannel,)
        #print "HEREEEEEEEEEEEEEE", self.inputs["Input"].shape ,self.outputs["Output"]._shape
        #print self.resultingChannels(), self.name
        
        #print self.outputs["Output"]._axistags
        if self.outputs["Output"]._axistags.axisTypeCount(vigra.AxisType.Channels) == 0:
            self.outputs["Output"]._axistags.insertChannelAxis()

    def resultingChannels(self):
        raise RuntimeError('resultingChannels() not implemented')
        

#difference of Gaussians
def differenceOfGausssians(image,sigma0, sigma1, out = None):
    """ difference of gaussian function"""        
    return (vigra.filters.gaussianSmoothing(image,sigma0)-vigra.filters.gaussianSmoothing(image,sigma1))


def firstHessianOfGaussianEigenvalues(image, sigmas):
    return vigra.filters.hessianOfGaussianEigenvalues(image, sigmas)[...,0]

def coherenceOrientationOfStructureTensor(image,sigma0, sigma1, out = None):
    """
    coherence Orientation of Structure tensor function:
    input:  M*N*1ch VigraArray
            sigma corresponding to the inner scale of the tensor
            scale corresponding to the outher scale of the tensor
    
    output: M*N*2 VigraArray, the firest channel correspond to coherence
                              the second channel correspond to orientation
    """
    
    #FIXME: make more general
    
    #assert image.spatialDimensions==2, "Only implemented for 2 dimensional images"
    assert len(image.shape)==2 or (len(image.shape)==3 and image.shape[2] == 1), "Only implemented for 2 dimensional images"
    
    st=vigra.filters.structureTensor(image, sigma0, sigma1)
    i11=st[:,:,0]
    i12=st[:,:,1]
    i22=st[:,:,2]
    
    if out is not None:
        assert out.shape[0] == image.shape[0] and out.shape[1] == image.shape[1] and out.shape[2] == 2
        res = out
    else:
        res=numpy.ndarray((image.shape[0],image.shape[1],2))
    
    res[:,:,0]=numpy.sqrt( (i22-i11)**2+4*(i12**2))/(i11-i22)
    res[:,:,1]=numpy.arctan(2*i12/(i22-i11))/numpy.pi +0.5
    
    
    return res




class OpDifferenceOfGaussians(OpBaseVigraFilter):
    name = "DifferenceOfGaussians"
    vigraFilter = staticmethod(differenceOfGausssians)
    outputDtype = numpy.float32 
    supportsOut = False
    inputSlots = [InputSlot("Input"), InputSlot("sigma0", stype = "float"), InputSlot("sigma1", stype = "float")]
    
    def resultingChannels(self):
        return 1

class OpCoherenceOrientation(OpBaseVigraFilter):
    name = "CoherenceOrientationOfStructureTensor"
    vigraFilter = staticmethod(coherenceOrientationOfStructureTensor)
    outputDtype = numpy.float32 
    inputSlots = [InputSlot("Input"), InputSlot("sigma0", stype = "float"), InputSlot("sigma1", stype = "float")]
    
    def resultingChannels(self):
        return 2    


class OpGaussianSmoothing(OpBaseVigraFilter):
    name = "GaussianSmoothing"
    vigraFilter = staticmethod(vigra.filters.gaussianSmoothing)
    outputDtype = numpy.float32 
        

    def resultingChannels(self):
        return 1

    
    def notifyConnectAll(self):
        OpBaseVigraFilter.notifyConnectAll(self)

    
class OpHessianOfGaussianEigenvalues(OpBaseVigraFilter):
    name = "HessianOfGaussianEigenvalues"
    vigraFilter = staticmethod(vigra.filters.hessianOfGaussianEigenvalues)
    outputDtype = numpy.float32 
    inputSlots = [InputSlot("Input"), InputSlot("scale", stype = "float")]

    def resultingChannels(self):
        temp = self.inputs["Input"].axistags.axisTypeCount(vigra.AxisType.Space)
        return temp


class OpStructureTensorEigenvalues(OpBaseVigraFilter):
    name = "StructureTensorEigenvalues"
    vigraFilter = staticmethod(vigra.filters.structureTensorEigenvalues)
    outputDtype = numpy.float32 
    inputSlots = [InputSlot("Input"), InputSlot("innerScale", stype = "float"),InputSlot("outerScale", stype = "float")]

    def resultingChannels(self):
        temp = self.inputs["Input"].axistags.axisTypeCount(vigra.AxisType.Space)
        return temp
    


class OpHessianOfGaussianEigenvaluesFirst(OpBaseVigraFilter):
    name = "First Eigenvalue of Hessian Matrix"
    vigraFilter = staticmethod(firstHessianOfGaussianEigenvalues)
    outputDtype = numpy.float32 
    supportsOut = False
    inputSlots = [InputSlot("Input"), InputSlot("scale", stype = "float")]

    def resultingChannels(self):
        return 1



class OpHessianOfGaussian(OpBaseVigraFilter):
    name = "HessianOfGaussian"
    vigraFilter = staticmethod(vigra.filters.hessianOfGaussian)
    outputDtype = numpy.float32 

    def resultingChannels(self):
        temp = self.inputs["Input"].axistags.axisTypeCount(vigra.AxisType.Space)*(self.inputs["Input"].axistags.axisTypeCount(vigra.AxisType.Space) + 1) / 2
        return temp
    
class OpGaussianGradientMagnitude(OpBaseVigraFilter):
    name = "GaussianGradientMagnitude"
    vigraFilter = staticmethod(vigra.filters.gaussianGradientMagnitude)
    outputDtype = numpy.float32 

    def resultingChannels(self):
        
        return 1

class OpLaplacianOfGaussian(OpBaseVigraFilter):
    name = "LaplacianOfGaussian"
    vigraFilter = staticmethod(vigra.filters.laplacianOfGaussian)
    outputDtype = numpy.float32 
    supportsOut = False
    inputSlots = [InputSlot("Input"), InputSlot("scale", stype = "float")]

    
    def resultingChannels(self):
        return 1

class OpOpening(OpBaseVigraFilter):
    name = "Opening"
    vigraFilter = staticmethod(vigra.filters.multiGrayscaleOpening)
    outputDtype = numpy.float32
    inputDtype = numpy.float32

    def resultingChannels(self):
        return 1

class OpClosing(OpBaseVigraFilter):
    name = "Closing"
    vigraFilter = staticmethod(vigra.filters.multiGrayscaleClosing)
    outputDtype = numpy.float32
    inputDtype = numpy.float32

    def resultingChannels(self):
        return 1

class OpErosion(OpBaseVigraFilter):
    name = "Erosion"
    vigraFilter = staticmethod(vigra.filters.multiGrayscaleErosion)
    outputDtype = numpy.float32
    inputDtype = numpy.float32

    def resultingChannels(self):
        return 1

class OpDilation(OpBaseVigraFilter):
    name = "Dilation"
    vigraFilter = staticmethod(vigra.filters.multiGrayscaleDilation)
    outputDtype = numpy.float32
    inputDtype = numpy.float32

    def resultingChannels(self):
        return 1



class OpImageReader(Operator):
    name = "Image Reader"
    category = "Input"
    
    inputSlots = [InputSlot("Filename", stype = "filestring")]
    outputSlots = [OutputSlot("Image")]
    
    def notifyConnectAll(self):
        filename = self.inputs["Filename"].value

        if filename is not None:
            info = vigra.impex.ImageInfo(filename)
            
            oslot = self.outputs["Image"]
            oslot._shape = info.getShape()
            oslot._dtype = info.getDtype()
            oslot._axistags = info.getAxisTags()
        else:
            oslot = self.outputs["Image"]
            oslot._shape = None
            oslot._dtype = None
            oslot._axistags = None

    def getOutSlot(self, slot, key, result):
        filename = self.inputs["Filename"].value
        temp = vigra.impex.readImage(filename)

        result[:] = temp[key]
        #self.outputs["Image"][:]=temp[:]
    
import glob
class OpFileGlobList(Operator):
    name = "Glob filenames to 1D-String Array"
    category = "Input"
    
    inputSlots = [InputSlot("Globstring", stype = "string")]
    outputSlots = [MultiOutputSlot("Filenames", stype = "filestring")]
    
    def notifyConnectAll(self):
        globstring = self.inputs["Globstring"].value
        
        self.filenames = glob.glob(globstring)        
        
        oslot = self.outputs["Filenames"]
        oslot.resize(len(self.filenames))
        for slot in oslot:
            slot._shape = (1,)
            slot._dtype = object
            slot._axistags = None
    
    def getSubOutSlot(self, slots, indexes, key, result):
        result[0] = self.filenames[indexes[0]]
    
    
    
    
    
class OpOstrichReader(Operator):
    name = "Ostrich Reader"
    category = "Input"
    
    inputSlots = []
    outputSlots = [OutputSlot("Image")]

    
    
    def __init__(self, g):
        Operator.__init__(self,g)
        #filename = self.filename = "/home/lfiaschi/graph-christoph/tests/ostrich.jpg"
        filename = self.filename = "/home/cstraehl/Projects/eclipse-workspace/graph/tests/ostrich.jpg"
        info = vigra.impex.ImageInfo(filename)
        
        oslot = self.outputs["Image"]
        oslot._shape = info.getShape()
        oslot._dtype = info.getDtype()
        oslot._axistags = info.getAxisTags()
    
    def getOutSlot(self, slot, key, result):
        temp = vigra.impex.readImage(self.filename)
        result[:] = temp[key]


class OpImageWriter(Operator):
    name = "Image Writer"
    category = "Output"
    
    inputSlots = [InputSlot("Filename", stype = "filestring" ), InputSlot("Image")]
    
    def notifyConnectAll(self):
        filename = self.inputs["Filename"].value

        imSlot = self.inputs["Image"]
        
        assert len(imSlot.shape) == 2 or len(imSlot.shape) == 3, "OpImageWriter: wrong image shape %r vigra can only write 2D images, with 1 or 3 channels" %(imSlot.shape,)

        axistags = copy.copy(imSlot.axistags)
        
        image = numpy.ndarray(imSlot.shape, dtype=imSlot.dtype)
        
        def closure(result):
            dtype = imSlot.dtype
            vimage = vigra.VigraArray(image, dtype = dtype, axistags = axistags)
            vigra.impex.writeImage(image, filename)

        self.inputs["Image"][:].writeInto(image).notify(closure)
    

class OpH5Reader(Operator):
    name = "H5 File Reader"
    category = "Input"
    
    inputSlots = [InputSlot("Filename", stype = "filestring"), InputSlot("hdf5Path", stype = "string")]
    outputSlots = [OutputSlot("Image")]
    
        
    def notifyConnectAll(self):
        filename = self.inputs["Filename"].value
        hdf5Path = self.inputs["hdf5Path"].value
        
        f = h5py.File(filename, 'r')
    
        d = f[hdf5Path]
        
        
        self.outputs["Image"]._dtype = d.dtype
        self.outputs["Image"]._shape = d.shape
        
        if len(d.shape) == 2:
            axistags=vigra.AxisTags(vigra.AxisInfo('x',vigra.AxisType.Space),vigra.AxisInfo('y',vigra.AxisType.Space))   
        else:
            axistags= vigra.VigraArray.defaultAxistags(len(d.shape))
        self.outputs["Image"]._axistags=axistags
        self.f=f
        self.d=self.f[hdf5Path]    
        
        
        #f.close()
        
        #FOR DEBUG DUMPING REQUEST TO A FILE
        #import os
        #logfile='readerlog.txt'
        #if os.path.exists(logfile): os.remove(logfile)
        
        #self.ff=open(logfile,'a')
        
        
    def getOutSlot(self, slot, key, result):
        filename = self.inputs["Filename"].value
        hdf5Path = self.inputs["hdf5Path"].value
        
        #f = h5py.File(filename, 'r')
    
        #d = f[hdf5Path]
        
        
        
        
        
        result[:] = self.d[key]
        #f.close()
        
        #Debug DUMPING REQUEST TO FILE
        #start,stop=roi.sliceToRoi(key,self.d.shape)
        #dif=numpy.array(stop)-numpy.array(start)
        
        #self.ff.write(str(start)+'   '+str(stop)+'   ***  '+str(dif)+' \n')
        

        
class OpH5Writer(Operator):
    name = "H5 File Writer"
    category = "Output"
    
    inputSlots = [InputSlot("Filename", stype = "filestring"), InputSlot("hdf5Path", stype = "string"), InputSlot("Image")]
    outputSlots = [OutputSlot("WriteImage")]

    def notifyConnectAll(self):        
        self.outputs["WriteImage"]._shape = (1,)
        self.outputs["WriteImage"]._dtype = object
#            filename = self.inputs["Filename"][0].allocate().wait()[0]
#            hdf5Path = self.inputs["hdf5Path"][0].allocate().wait()[0]
#
#            imSlot = self.inputs["Image"]
#            
#            axistags = copy.copy(imSlot.axistags)
#            
#            image = numpy.ndarray(imSlot.shape, dtype=imSlot.dtype)
#                        
#            def closure():
#                f = h5py.File(filename, 'w')
#                g = f
#                pathElements = hdf5Path.split("/")
#                for s in pathElements[:-1]:
#                    g = g.create_group(s)
#                g.create_dataset(pathElements[-1],data = image)
#                f.close()
#    
#            self.inputs["Image"][:].writeInto(image).notify(closure)
    
    def getOutSlot(self, slot, key, result):
        filename = self.inputs["Filename"].value
        hdf5Path = self.inputs["hdf5Path"].value

        imSlot = self.inputs["Image"]
        
        axistags = copy.copy(imSlot.axistags)
        
        image = numpy.ndarray(imSlot.shape, dtype=imSlot.dtype)
                    

        self.inputs["Image"][:].writeInto(image).wait()
        
        
        f = h5py.File(filename, 'w')
        g = f
        pathElements = hdf5Path.split("/")
        for s in pathElements[:-1]:
            g = g.create_group(s)
        g.create_dataset(pathElements[-1],data = image)
        f.close()
        
        result[0] = True
        
        
        
class OpH5WriterBigDataset(Operator):
    name = "H5 File Writer BigDataset"
    category = "Output"
    
    inputSlots = [InputSlot("Filename", stype = "filestring"), InputSlot("hdf5Path", stype = "string"), InputSlot("Image")]
    outputSlots = [OutputSlot("WriteImage")]

    def notifyConnectAll(self):    
        self.outputs["WriteImage"]._shape = (1,)
        self.outputs["WriteImage"]._dtype = object
        
        
        
        filename = self.inputs["Filename"].value
        import os
        if os.path.exists(filename): os.remove(filename)
        
        hdf5Path = self.inputs["hdf5Path"].value
        self.f = h5py.File(filename, 'w')
        
        g=self.f
        pathElements = hdf5Path.split("/")
        for s in pathElements[:-1]:
            g = g.create_group(s)
        
        print self.inputs['Image'].shape
        #FIXME:
        #change that to the real shape after testing
        shape=self.inputs['Image'].shape
        #shape = (1, 10, 10, 10, 1)
        
        self.d=g.create_dataset(pathElements[-1],shape=shape,dtype=numpy.float32, chunks=(1,128,128,1,1),\
                                compression='gzip', compression_opts=4)

    
    def getOutSlot(self, slot, key, result):
        
        requests=self.computeRequests()
        
        
        imSlot = self.inputs["Image"]
        
                    
        for r in requests:
            self.d[r]=self.inputs["Image"][r].allocate().wait()

        result[0] = True
        
        
    def computeRequests(self):
        
        #TODO: reimplement the request better
        shape=numpy.asarray(self.inputs['Image'].shape)
        
        
        
        
        start=numpy.asarray([0]*len(shape))
        
        block=numpy.asarray(shape)
        
        
        
        reqList=[]
        
        
        for z in xrange(1,shape[3]):
            block[3]=z
            reqList.append(roiToSlice(start,block))
        
        return reqList
    
    def close(self):
        self.f.close()
        
        
        
        
        
        
                

class OpH5ReaderBigDataset(Operator):
    
    name = "H5 File Reader For Big Datasets"
    category = "Input"
    
    inputSlots = [InputSlot("Filenames"), InputSlot("hdf5Path", stype = "string")]
    outputSlots = [OutputSlot("Output")]
    
    def __init__(self, graph):
        Operator.__init__(self, graph)
        
        self._lock = Lock()
        
    def notifyConnectAll(self):
        filename = str(self.inputs["Filenames"].value[0])
        hdf5Path = self.inputs["hdf5Path"].value
        
        f = h5py.File(filename, 'r')
    
        d = f[hdf5Path]
        
        self.shape=d.shape
        
        self.outputs["Output"]._dtype = d.dtype
        self.outputs["Output"]._shape = d.shape
        
        if len(d.shape) == 5:
            axistags= vigra.VigraArray.defaultAxistags('txyzc')
        else:
            print "Not implemented"
            raise
        self.outputs["Output"]._axistags=axistags
            
        f.close()
        
        self.F=[]
        self.D=[]
        self.ChunkList=[]
        
        for filename in self.inputs["Filenames"].value:
            filename = str(filename)
            f=h5py.File(filename, 'r')
            d=f[hdf5Path]
            
            assert (numpy.array(self.shape)==numpy.array(self.shape)).all(), "Some files have a different shape, this is not allowed man!"
            
            
            self.ChunkList.append(d.chunks)
            self.F.append(f)
            self.D.append(d)
        
    def getOutSlot(self, slot, key, result):
        filenames = self.inputs["Filenames"].value
        
        hdf5Path = self.inputs["hdf5Path"].value
        F=[]
        D=[]
        ChunkList=[]
        
        start,stop=sliceToRoi(key,self.shape)
        diff=numpy.array(stop)-numpy.array(start)

        maxError=sys.maxint
        index=0

        self._lock.acquire()
        #lock access to self.ChunkList,
        #               self.D
        for i,chunks in enumerate(self.ChunkList):
            cs = numpy.array(chunks)
            
            error = numpy.sum(numpy.abs(diff -cs))
            #print error
            if error<maxError:
                index = i
                maxError = error
        
#        print "best error", maxError
#        print "selected chunking", self.ChunkList[index], "for request", diff
        
        result[:]=self.D[index][key]
        self._lock.release()
    """
    def notifyDisconnect(self, slot):
        for f in self.F:
            f.close()
        self.D=[]
        self.ChunkList=[]
    """