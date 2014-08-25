import os
import tempfile
import cPickle as pickle
from GPy import kern
import numpy
import h5py

import GPy
from .lazyflowClassifier import LazyflowVectorwiseClassifierABC, LazyflowVectorwiseClassifierFactoryABC

import logging
logger = logging.getLogger(__name__)

class GaussianProcessClassifierFactory(LazyflowVectorwiseClassifierFactoryABC):
    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs
    
    def create_and_train(self, X, y):
        logger.debug( 'training single-threaded GaussianProcessClassifier' )
        
        # Save for future reference
        known_labels = numpy.unique(y)
        
        X = numpy.asarray(X, numpy.float32)
        y = numpy.asarray(y, numpy.uint32)
        if y.ndim == 1:
            y = y[:, numpy.newaxis]
        
        y-=1 #TODO: Don't do this.
        assert X.ndim == 2
        assert len(X) == len(y)
        assert all(i in (0,1) for i in numpy.unique(y))
        
        # get control of default parameters
        if not "kernel" in self._kwargs:
            self._kwargs["kernel"]=kern.rbf(X.shape[1])
        if not "num_inducing" in self._kwargs:
            self._kwargs["num_inducing"]=50
        classifier = GPy.models.SparseGPClassification(X,
                                                       y,
                                                        **self._kwargs)
        print "y",y
        classifier.tie_params('.*len')
        #print classifier
        classifier.update_likelihood_approximation()
        classifier.optimize(max_iters=100)
        return GaussianProcessClassifier( classifier, known_labels )

    @property
    def description(self):
        return "Gaussian Process Classifier"

assert issubclass( GaussianProcessClassifierFactory, LazyflowVectorwiseClassifierFactoryABC )

class GaussianProcessClassifier(LazyflowVectorwiseClassifierABC):
    """
    Adapt the vigra RandomForest class to the interface lazyflow expects.
    """
    def __init__(self, gpc, known_labels):
        self._known_labels = known_labels
        self._gpc = gpc
    
    def predict_probabilities(self, X, with_variance = False):
        logger.debug( 'predicting single-threaded vigra RF' )
        
        probs,var,_,_ = self._gpc.predict(numpy.asarray(X, dtype=numpy.float32) )
        #we get the probability p for label 1 here,
        #so we complete the table by adding the probability for label 0, which is 1-p
        print var
        if with_variance:
            return numpy.concatenate((1-probs,probs),axis = 1),var
        return  numpy.concatenate((1-probs,probs),axis = 1)
    
    @property
    def known_classes(self):
        return self._known_labels
    
    def serialize_hdf5(self):
        print "should not get here"
        pass
    
    def deserialize_hdf5(self):
        print "should not get here"
        pass

assert issubclass( GaussianProcessClassifier, LazyflowVectorwiseClassifierABC )
