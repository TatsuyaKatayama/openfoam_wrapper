from openfoam_wrapper.openfoam_wrapper import OpenFOAM_wrapper

from openmdao.lib.drivers.api import BroydenSolver
from openmdao.main.api import Assembly


class SolutionAssembly(Assembly):
    """ Solves for Cavity. """

    def configure(self):
        #add instance
        self.add('driver', BroydenSolver())
        self.add('cavity', OpenFOAM_wrapper())
        
        #edit cavity
        self.cavity.case_dir = "cavity"
        self.cavity.foamEditKeywords['constant/transportProperties.nu'] = '"nu [0 2 -1 0 0 0 0] %s" %(nu)'
        self.cavity.foamGetTimelineKeywords['press1'] = 'postProcessing/probes/0/p|1'
        self.cavity.nu = 0.1

        #edit driver
        self.driver.workflow.add('cavity')
        self.driver.add_parameter('cavity.nu', low=0.0001, high=0.1, scaler=0.01)
        self.driver.add_constraint('cavity.press1.latestTimeValue = 2.9242')

        
if __name__ == "__main__":

    assy = SolutionAssembly()
    assy.run()
    
    print "nu,pressure1 = (%f, %f)" % (assy.cavity.nu, assy.cavity.press1.latestTimeValue)

