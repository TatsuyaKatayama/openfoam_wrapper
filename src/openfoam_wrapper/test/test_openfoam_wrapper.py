import tempfile
import unittest
import os
import shutil

from openmdao.main.datatypes.api import Float, Dict

from PyFoam.RunDictionary.SolutionDirectory import SolutionDirectory

try:
    from openfoam_wrapper.openfoam_wrapper import OpenFOAM_wrapper
except ImportError:
    pass


edit_dicts = {"constant/polyMesh/blockMeshDict.vertices[0]":'"(%s -0.01 0)" %(x0)',
             u"constant/polyMesh/blockMeshDict.convertToMeters":u'"%s" %(x1)',
             "0/U.boundaryField.movingWall.value":'"uniform (%s 0 %s)" %(x2,x3)'}

analysis_logs = {"y0":'log.blockMesh|  nCells: (.+)',
    "y1":"log.simpleFoam|DICPCG:  Solving for p, Initial residual = (.+?),"}

get_timelines = {"y2":"postProcessing/probes/0/p|1",
             u"constant/polyMesh/blockMeshDict.convertToMeters":u'"%s" %(x1)',
             "0/U.boundaryField.movingWall.value":'"uniform (%s 0 %s)" %(x2,x3)'}
             
class Cavity(OpenFOAM_wrapper):
    foamEditKeywords = Dict(edit_dicts, iotype='in', desc='default All')
    foamEditKeywords = Dict(edit_dicts, iotype='in', desc='default All')
    x0 = Float(-0.01, iotype='in', desc='class variale')
    x1 = Float(0.11, iotype='in', desc='class variale')


class OpenFOAM_wrapperTestCase(unittest.TestCase):
       
    def setUp(self):
        cavityTut = os.path.join(os.getenv("FOAM_TUTORIALS"),
                                "incompressible/icoFoam/cavity")
        if not os.path.exists(cavityTut):
            unittest.SkipTest("need $FOAM_TUTORIALS/incompressible/cavity \
                               for unittest.")

        try:
            self.tmpDir = tempfile.mkdtemp()
            cavityCase = SolutionDirectory(os.path.join(self.tmpDir,"cavity"))
            shutil.copytree(cavityTut, cavityCase.name)
        except:
            unittest.SkipTest("can not copy cavity case to temp_dir.")   
                 
        #create Allrun 
        fp = open(os.path.join(cavityCase.name,"Allrun"),'w')
        fp.write('#!/bin/sh\nblockMesh>log.blockMesh\nicoFoam>log.icoFoam\n')
        fp.close()   
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
        shutil.rmtree(self.tmpDir)
        
    def test_init(self):
        """check variables(x0,x1,x2,x3,y0,y1) added automation."""
        
        try:
            self.cavity = Cavity()
        except RuntimeError:
            unittest.SkipTest("not found icoFoam. check the $PATH.")

        #check variable x0,x1,x2,x3 in self.cavity instance 
        self.assertTrue(hasattr(self.cavity, "x0"))
        self.assertTrue(hasattr(self.cavity, "x1"))
        self.assertTrue(hasattr(self.cavity, "x2"))
        self.assertTrue(hasattr(self.cavity, "x3"))
        #check variable x0,x1,x2,x3 in Cavity Class.                       
        self.assertTrue(hasattr(Cavity, "x0"))
        self.assertTrue(hasattr(Cavity, "x1"))
        self.assertFalse(hasattr(Cavity, "x2"))
        self.assertFalse(hasattr(Cavity, "x3"))
        #check variable y0,y1
        self.assertTrue(hasattr(self.cavity, "y0"))
        self.assertTrue(hasattr(self.cavity, "y1"))
        
        self.cavity.case_dir = os.path.join(self.tmpDir,"cavity")
        
    # add some tests here...
    
    #def test_Openfoam_wrapper(self):
        #pass
        
if __name__ == "__main__":
    unittest.main()
    
