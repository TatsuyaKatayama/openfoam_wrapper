import tempfile
import unittest
import os
import shutil

from openmdao.main.datatypes.api import Float, Dict

from PyFoam.RunDictionary.SolutionDirectory import SolutionDirectory
from PyFoam.FoamInformation import foamTutorials
from PyFoam.FoamInformation import foamVersionNumber

try:
    from openfoam_wrapper.openfoam_wrapper import OpenFOAM_wrapper
except ImportError:
    pass


edit_dicts = \
    {"constant/polyMesh/blockMeshDict.vertices[0]":'"(%s -0.01 0)" %(x0)',
     u"constant/polyMesh/blockMeshDict.convertToMeters":u'"%s" %(x1)',
     "0/U.boundaryField.movingWall.value":'"uniform (%s 0 %s)" %(x2,x3)'}

analysis_logs = \
    {u"y0":u"log.icoFoam|DICPCG:  Solving for p, Initial residual = (.+?),"}

get_timelines = \
    {"y1":"postProcessing/probes/0/p|1",
     u"y2":u'postProcessing/probes/0/U|2'}
             
class Cavity(OpenFOAM_wrapper):
    foamEditKeywords = Dict(edit_dicts, iotype='in', desc='')
    foamAnalyzedKeywords = Dict(analysis_logs, iotype='in', desc='')
    foamGetTimelineKeywords = Dict(get_timelines, iotype='in', desc='')
    x0 = Float(-0.01, iotype='in', desc='class variale')
    x1 = Float(0.11, iotype='in', desc='class variale')


class OpenFOAM_wrapperTestCase(unittest.TestCase):
       
    def setUp(self):
        if not foamVersionNumber() == (2,3):
            raise unittest.SkipTest("need ver.2.3  for this unittest.")
        
        cavityTut = os.path.join(foamTutorials(),
                                "incompressible/icoFoam/cavity")
        if not os.path.exists(cavityTut):
            raise unittest.SkipTest("need $FOAM_TUTORIALS/incompressible/cavity \
                               for unittest.")

        try:
            self.tmpDir = tempfile.mkdtemp()
            shutil.copytree(cavityTut, os.path.join(self.tmpDir,"cavity"))
            cavityCase = SolutionDirectory(os.path.join(self.tmpDir,"cavity"))
        except:
            raise unittest.SkipTest("can not copy cavity case to temp_dir.")   
                 
        #create Allrun 
        fp = open(os.path.join(cavityCase.name,"Allrun"),'w')
        fp.write('#!/bin/sh\nblockMesh>log.blockMesh\nicoFoam>log.icoFoam\n')
        fp.close()  
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
            ( 0.1 0.0925 0.005 )
        );
    }
}
"""
        fp = open(cavityCase.controlDict(),'a')
        fp.write(fObj)
        fp.close()
        
    def tearDown(self):
#        print(self.tmpDir)
        shutil.rmtree(self.tmpDir)
        
    def test_standard(self):
        """standard check"""
        
        try:
            self.cavity = Cavity()
        except RuntimeError:
            raise unittest.SkipTest("not found icoFoam. check the $PATH.")

        #check variable x0,x1,x2,x3 in self.cavity instance 
        self.assertTrue(hasattr(self.cavity, "x0"))
        self.assertTrue(hasattr(self.cavity, "x1"))
        self.assertTrue(hasattr(self.cavity, "x2"))
        self.assertTrue(hasattr(self.cavity, "x3"))
        #check variable y0,y1
        self.assertTrue(hasattr(self.cavity, "y0"))
        self.assertTrue(hasattr(self.cavity, "y1"))
        self.assertTrue(hasattr(self.cavity, "y2"))
        
        self.cavity.case_dir = os.path.join(self.tmpDir,"cavity")
        self.cavity.x2 = 1.0
        self.cavity.x3 = -0.00001
        self.cavity.run()
        
        self.assertEqual(self.cavity.y0.latestTimeValue,9.98257e-07)
        self.assertEqual(self.cavity.y1.latestTimeValue,0.924818)
        self.assertEqual(self.cavity.y2.latestTimeValue,-0.358678)
               
    # add some tests here...
    
    #def test_Openfoam_wrapper(self):
        #pass
        
if __name__ == "__main__":
    unittest.main()
    
