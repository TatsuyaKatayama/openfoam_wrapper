from openfoam_wrapper.openfoam_wrapper import OpenFOAM_wrapper
from openfoam_wrapper.openfoam_wrapper import TimeLineValue

from openmdao.lib.drivers.api import BroydenSolver
from openmdao.main.api import Assembly
from openmdao.main.datatypes.api import Float, Dict, VarTree


class Cavity(OpenFOAM_wrapper):
    """
    cavity case. Execute the Crear-case,Edit-nu,Allrun and Get-timeline.
    """
    case_dir = "cavity"
    nu = Float(0.1, iotype='in')
    press1 = VarTree(TimeLineValue(), iotype='out')
    foamEditKeywords = Dict({'constant/transportProperties.nu': \
                       '"nu [0 2 -1 0 0 0 0] %s" %(nu)'}, iotype='in')
    foamGetTimelineKeywords = Dict({'press1': \
                              'postProcessing/probes/0/p|1'}, iotype='in')
    

class SolutionAssembly(Assembly):
    """ Solves for Cavity. """

    def configure(self):

        self.add('driver', BroydenSolver())
        self.add('cavity', Cavity())

        self.driver.workflow.add('cavity')

        self.driver.add_parameter('cavity.nu', low=0.0001, \
                                 high=0.1, scale=0.001)

        self.driver.add_constraint('cavity.press1.latestTimeValue = 2.9242')

        
if __name__ == "__main__":

    assy = SolutionAssembly()
    assy.run()
    
    print "\n"
    print "nu,pressure1 = (%f, %f)" % (assy.cavity.nu, \
                                     assy.cavity.press1.latestTimeValue)

