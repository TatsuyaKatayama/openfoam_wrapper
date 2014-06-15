import tempfile
import unittest
import os
import shutil

from openmdao.main.api import Assembly, Component, SequentialWorkflow, set_as_top
from openmdao.main.datatypes.api import Float, Dict
from openmdao.lib.drivers.api import DOEdriver
from openmdao.lib.doegenerators.api import FullFactorial
from openmdao.lib.casehandlers.api import DBCaseRecorder
from openmdao.lib.surrogatemodels.api import FloatKrigingSurrogate, ResponseSurface
from pyopt_driver.pyopt_driver import pyOptDriver
from openmdao.lib.drivers.api import BroydenSolver

from PyFoam.RunDictionary.SolutionDirectory import SolutionDirectory
from PyFoam.FoamInformation import foamTutorials
from PyFoam.FoamInformation import foamVersionNumber

try:
    from openfoam_wrapper.openfoam_wrapper import OpenFOAM_wrapper
    from openfoam_wrapper.openfoam_wrapper import FoamMetaModel
    from pyopt_driver.pyopt_driver import pyOptDriver
except ImportError:
    pass

class BroydenCavityInstance(Assembly):
    """ Solves for Cavity. """

    def configure(self):
        #add instance
        self.add('driver', BroydenSolver())
        self.add('cavity', OpenFOAM_wrapper())
        
        #edit cavity
        #self.cavity.case_dir = "cavity"
        self.cavity.foamEditKeywords['constant/transportProperties.nu'] = '"nu [0 2 -1 0 0 0 0] %s" %(nu)'
        self.cavity.foamGetTimelineKeywords['press1'] = 'postProcessing/probes/0/p|1'
        self.cavity.nu = 0.1

        #edit driver
        self.driver.workflow.add('cavity')
        self.driver.add_parameter('cavity.nu', low=0.0001, high=0.1, scaler=0.01)
        self.driver.add_constraint('cavity.press1.latestTimeValue = 2.9242')
        

class DeformationCavity(OpenFOAM_wrapper):
    # Finds the minimum f(1) and f(2)
    # 

    x1 = Float(0.0, iotype='in', desc='The variable x1')
    x2 = Float(1.0, iotype='in', desc='The variable x2')
   
    foamEditKeywords = Dict(
        {"constant/polyMesh/blockMeshDict.vertices[0]":'"(%s 0 0)" %(x1)',
         "constant/polyMesh/blockMeshDict.vertices[4]":'"(%s 0 0.1)" %(x1)',
         "constant/polyMesh/blockMeshDict.vertices[1]":'"(%s 0 0)" %(x2)',
         "constant/polyMesh/blockMeshDict.vertices[5]":'"(%s 0 0.1)" %(x2)'},
         iotype='in', desc='')
         
    foamGetTimelineKeywords = Dict(
        {"f1":"postProcessing/probes/0/p|1",
         "f2":'postProcessing/probes/0/p|2'},
         iotype='in', desc='')

class MultiObjectiveCavity(Assembly):

    def configure(self):

        #Components
        self.add("DeformationCavity_meta",FoamMetaModel())
        self.DeformationCavity_meta.includes=['x1','x2','f1','f2']
        
        self.DeformationCavity_meta.model = DeformationCavity()
        self.DeformationCavity_meta.default_surrogate = ResponseSurface()
        
        self.DeformationCavity_meta.surrogates["f1.latestTimeValue"] = FloatKrigingSurrogate()
        self.DeformationCavity_meta.surrogates["f2.latestTimeValue"] = FloatKrigingSurrogate()
        self.DeformationCavity_meta.surrogates["f1.latestTimeValue"].nugget = 0.0
        self.DeformationCavity_meta.surrogates["f2.latestTimeValue"].nugget = 0.0
        
        
        self.DeformationCavity_meta.recorder = DBCaseRecorder()

        #Training the MetaModel
        self.add("DOE_Trainer",DOEdriver())
        self.DOE_Trainer.DOEgenerator = FullFactorial()
        self.DOE_Trainer.DOEgenerator.num_levels = 4
        self.DOE_Trainer.add_parameter('DeformationCavity_meta.x1', low= -0.1, high=0.1)
        self.DOE_Trainer.add_parameter('DeformationCavity_meta.x2', low=  0.9, high=1.1)
        
        self.DOE_Trainer.case_outputs = ["DeformationCavity_meta.f1.latestTimeValue",
                                        "DeformationCavity_meta.f2.latestTimeValue"]
        
        self.DOE_Trainer.record_doe = False                                
        self.DOE_Trainer.add_event("DeformationCavity_meta.train_next")
        self.DOE_Trainer.recorders = [DBCaseRecorder()]

        #MetaModel Validation
        self.add("DeformationCavity", DeformationCavity())
        self.add("DOE_Validate", DOEdriver())
        self.DOE_Validate.DOEgenerator = FullFactorial()
        self.DOE_Validate.DOEgenerator.num_levels = 3
        self.DOE_Validate.add_parameter(("DeformationCavity_meta.x1", "DeformationCavity.x1"), low=-0.1, high=0.1)
        self.DOE_Validate.add_parameter(("DeformationCavity_meta.x2", "DeformationCavity.x2"), low= 0.9, high=1.1)
                                     
        self.DOE_Validate.case_outputs = ["DeformationCavity.f1.latestTimeValue",
                                          "DeformationCavity.f2.latestTimeValue",
                                          "DeformationCavity_meta.f1.latestTimeValue", 
                                          "DeformationCavity_meta.f2.latestTimeValue"]
                                        
        self.DOE_Validate.record_doe = False                                
        self.DOE_Validate.recorders = [DBCaseRecorder()]
        
        # Create NSGA2 Optimizer instance
        self.add('NSGA2', pyOptDriver())
        self.NSGA2.print_results = True

        # NSGA2 Objective
        self.NSGA2.add_objective('DeformationCavity_meta.f1.latestTimeValue')
        self.NSGA2.add_objective('DeformationCavity_meta.f2.latestTimeValue')
        # NSGA2 Design Variable
        self.NSGA2.add_parameter('DeformationCavity_meta.x1', low=-0.1, high=0.1)
        self.NSGA2.add_parameter('DeformationCavity_meta.x2', low= 0.9, high=1.1)
        # NSGA2 Constraints
#        self.NSGA2.add_constraint('DeformationCavity_meta.x2 - DeformationCavity_meta.x1 >= 1.0')

        self.NSGA2.optimizer = 'NSGA2'
        optdict = {}
        optdict['PopSize'] = 100     #   a multiple of 4
        optdict['maxGen'] = 5
        optdict['pCross_real'] = 0.6 #prob of crossover of design variables in range (0.6-1.0)
        optdict['pMut_real'] = 0.5   #prob of mutation of (1/design varaibles)
        optdict['eta_c'] = 10.0      #distribution index for crossover in range (5 - 20)
        optdict['eta_m'] = 50.0      #distribution index for mutation in range (5 - 50)
        optdict['pCross_bin'] = 1.0  #prob of crossover of binary variable in range(0.6 - 1.0)
        optdict['pMut_real'] = 1.0   #prob of mutation of binary variables in (1/nbits)
        optdict['PrintOut'] = 1      #flag to turn on output to files (0-None, 1-Subset,2-All)
        optdict['seed'] = 0.0        #random seed number (0-autoseed based on time clock)

        self.NSGA2.options = optdict
                
        #Iteration Hierarchy
        self.driver.workflow = SequentialWorkflow()
        self.driver.workflow.add(['DOE_Trainer','DOE_Validate','NSGA2'])
        self.DOE_Trainer.workflow.add('DeformationCavity_meta')
        self.DOE_Validate.workflow.add('DeformationCavity_meta')
        self.DOE_Validate.workflow.add('DeformationCavity')
        # Driver process definition
        self.NSGA2.workflow.add('DeformationCavity_meta') 

class OpenFOAM_wrapperTestCase(unittest.TestCase):
       
    def setUp(self):
        self.tmpDir = tempfile.mkdtemp()     

    def tearDown(self):
        shutil.rmtree(self.tmpDir)
        
    def test_with_broyden(self):
        """
        broyden test
        """
        if not foamVersionNumber() in [(2,3),(2,2)]:
            raise unittest.SkipTest("need ver.2.3 or 2.2 for this unittest.")
        
        cavityTut = os.path.join(foamTutorials(),
                                "incompressible/icoFoam/cavity")

        if not os.path.exists(cavityTut):
            raise unittest.SkipTest("need $FOAM_TUTORIALS/incompressible/cavity \
                               for unittest.")

        try:
            shutil.copytree(cavityTut, os.path.join(self.tmpDir,"cavity"))
            cavityCase = SolutionDirectory(os.path.join(self.tmpDir,"cavity"))
        except:
            raise unittest.SkipTest("can not copy cavity case to temp_dir.")   
                 
        #create Allrun 
        with open(os.path.join(cavityCase.name,"Allrun"),'w') as fp:
            fp.write('#!/bin/sh\nblockMesh>log.blockMesh\nicoFoam>log.icoFoam\n')
        os.chmod(os.path.join(cavityCase.name,"Allrun"),0777)
         
        #append controlDict
        fObj="""
functions
{
    probes
    {
        type            probes;
        functionObjectLibs ("libsampling.so");
        enabled         true;
        outputControl   timeStep;
        outputInterval  1;
        fields
        (
            p
        );
        probeLocations
        (
            ( 0.1 0.0925 0.005 )
        );
    }
}
"""
        with open(cavityCase.controlDict(),'a') as fp:
            fp.write(fObj)
        
        #test start
        sim = set_as_top(BroydenCavityInstance())
        sim.cavity.case_dir = cavityCase.name
        sim.run()
        self.assertEqual(round(sim.cavity.nu,4),0.01)
        
    def test_with_moga(self):
        """
        moga test with pyopt_driver.
        create meta and optimization with nsga2.
        """
        if not foamVersionNumber() in [(2,3),(2,2)]:
            raise unittest.SkipTest("need ver.2.3 or 2.2 for this unittest.")
        
        cavityTut = os.path.join(foamTutorials(),
                                "incompressible/icoFoam/cavity")

        if not os.path.exists(cavityTut):
            raise unittest.SkipTest("need $FOAM_TUTORIALS/incompressible/cavity \
                               for unittest.")

        try:
            shutil.copytree(cavityTut, os.path.join(self.tmpDir,"cavity"))
            cavityCase = SolutionDirectory(os.path.join(self.tmpDir,"cavity"))
        except:
            raise unittest.SkipTest("can not copy cavity case to temp_dir.")   
                 
        #create Allrun 
        with open(os.path.join(cavityCase.name,"Allrun"),'w') as fp:
            fp.write('#!/bin/sh\nblockMesh>log.blockMesh\nicoFoam>log.icoFoam\n')
        os.chmod(os.path.join(cavityCase.name,"Allrun"),0777)
         
        #append controlDict
        fObj="""
functions
{
    probes
    {
        type            probes;
        functionObjectLibs ("libsampling.so");
        enabled         true;
        outputControl   timeStep;
        outputInterval  1;
        fields
        (
            p U
        );
        probeLocations
        (
            ( 0.015 0.015 0.005 )
            ( 0.085 0.015 0.005 )
        );
    }
}
"""
        with open(cavityCase.controlDict(),'a') as fp:
            fp.write(fObj)
        
        #test start
        sim = set_as_top(MultiObjectiveCavity())
        sim.DeformationCavity_meta.model.case_dir = cavityCase.name
        sim.DeformationCavity.case_dir = cavityCase.name
        try:
            sim.NSGA2.optimizer = 'NSGA2'
        except ValueError:
            raise SkipTest("NSGA2 not present on this system")
        sim.NSGA2.options['PrintOut'] = 0
        sim.run()        

       
    # add some tests here...
    
    #def test_Openfoam_wrapper(self):
        #pass
        
if __name__ == "__main__":
    unittest.main()
    
