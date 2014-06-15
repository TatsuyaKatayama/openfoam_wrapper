"""
OpenMDAO Wrapper for OpenFOAM with PyFoam.
"""
from openmdao.main.api import Component, VariableTree
from openmdao.main.datatypes.api import Float, Int, Str, Dict, Array, VarTree, Bool
from openmdao.main.datatypes.list import List
from openmdao.lib.components.external_code import ExternalCode
from openmdao.lib.components.api import MetaModel

from PyFoam.RunDictionary.SolutionDirectory import SolutionDirectory
from PyFoam.RunDictionary.ParsedParameterFile import ParsedParameterFile
from PyFoam.LogAnalysis.SimpleLineAnalyzer import GeneralSimpleLineAnalyzer
from PyFoam.LogAnalysis.FoamLogAnalyzer import FoamLogAnalyzer
from PyFoam.LogAnalysis.LogAnalyzerApplication import LogAnalyzerApplication
from PyFoam.RunDictionary.TimelineDirectory import TimelineDirectory

import os
import shlex
import string
import numpy

class FoamMetaModel(MetaModel):
    def check_config(self):
        '''Called as part of pre_execute.'''

        # 1. model must be set
        if self.model is None:
            self.raise_exception("MetaModel object must have a model!",
                                 RuntimeError)

        # 2. can't have both includes and excludes
        if self.excludes and self.includes:
            self.raise_exception("includes and excludes are mutually exclusive",
                                 RuntimeError)

        # 3. the includes and excludes must match actual inputs and outputs of the model
        input_names = self.surrogate_input_names()
        output_names = self.surrogate_output_names()
        #input_and_output_names = input_names + output_names
        input_and_output_names = [ (n + ".")[:(n + ".").find(".")] for n in (input_names + output_names)]
        for include in self.includes:
            if include not in input_and_output_names:
                self.raise_exception('The include "%s" is not one of the '
                                     'model inputs or outputs ' % include, ValueError)
        for exclude in self.excludes:
            if exclude not in input_and_output_names:
                self.raise_exception('The exclude "%s" is not one of the '
                                     'model inputs or outputs ' % exclude, ValueError)

        # 4. Either there are no surrogates set and no default surrogate
        #    ( just do passthrough )
        #        or
        #    all outputs must have surrogates assigned either explicitly
        #    or through the default surrogate
        if self.default_surrogate is None:
            no_sur = []
            for name in self.surrogate_output_names():
                if not self.surrogates[name]:
                    no_sur.append(name)
            if len(no_sur) > 0 and len(no_sur) != len(self._surrogate_output_names):
                self.raise_exception("No default surrogate model is defined and"
                                     " the following outputs do not have a"
                                     " surrogate model: %s. Either specify"
                                     " default_surrogate, or specify a"
                                     " surrogate model for all outputs." %
                                     no_sur, RuntimeError)

        # 5. All the explicitly set surrogates[] should match actual outputs of the model
        for surrogate_name in self.surrogates.keys():
            if surrogate_name not in output_names:
                self.raise_exception('The surrogate "%s" does not match one of the '
                                     'model outputs ' % surrogate_name, ValueError)


class FoamBaseComponent(Component):
    """This class is base Component to execute OpenFOAM pre,main and post commands"""
    case_dir = Str("", iotype="in", desc='OpenFOAM Case Dir. Absolute path or relative path in $FOAM_RUN.')
    force_fd = Bool(True, iotype='in', framework_var=True, deriv_ignore=True,
                    desc="If True, always finite difference this component.")

    def __init__(self):
        """Component.__init__() and check the path to icoFoam."""
        super(FoamBaseComponent, self).__init__()

        self.foam_case = None
        #Check OpenFOAM commands in $PATH.
        if not self._which("icoFoam"):
            self.raise_exception("OpenFOAM command is not found. Check $PATH.", RuntimeError)

        if not self.case_dir == '':
            caseDir = self.getPath(self.case_dir, False)
            
            if not caseDir == None:
                #type(caseDir) is str or unicode
                self.foam_case = SolutionDirectory(str(caseDir))

    def check_config(self):
        if not self.foam_case and self.case_dir == "":
            self.raise_exception("Not set self.case_dir.", RuntimeError)
    
        if not os.path.exists(self.foam_case.controlDict()):
            self.raise_exception("%s is not found. Check self.case_dir." % (self.foam_case.controlDict()),
                                 RuntimeError)

    def _which(self, cmd):
        """which command with python."""
        def is_exe(val):
            return os.path.isfile(val) and os.access(val, os.X_OK)

        fpath, fname = os.path.split(cmd)
        if fpath:
            if is_exe(cmd):
                return cmd
        else:        
            for path in os.environ["PATH"].split(os.pathsep):
                path = path.strip('"')
                exe_file = os.path.join(path, cmd)
                if is_exe(exe_file):
                    return exe_file
        return None
        
    def getPath(self, fdpath, riseError=True):
        """check and get the absolute path or relative path in $FOAM_RUN.""" 
        if os.path.exists(fdpath):
            return fdpath
            
        bool_foam_run = True
        foam_run = ""
        try:
            foam_run = os.environ['FOAM_RUN']
            fpath = os.path.join(foam_run, fdpath)
        except KeyError:
            bool_foam_run = False
        
        if bool_foam_run and os.path.exists(fpath):
            return fpath
            
        if riseError:
            self.raise_exception(" '%s' was not found." % fdpath, RuntimeError)
        return None
                
    def _input_trait_modified(self, obj, name, old, new):
        """hook th changing a trait."""
        super(FoamBaseComponent, self)._input_trait_modified(obj, name, old, new)
        if name == 'case_dir':
            caseDir = self.getPath(new,False)
            
            if not caseDir == None:
                #type(caseDir) is str or unicode
                self.foam_case = SolutionDirectory(str(caseDir))
            else:
                self.raise_exception("case_dir '%s' was"
                                         " not found." % new, RuntimeError)

class FoamClearCase(FoamBaseComponent):
    """Cleaning Case Directory with  PyFoam.RunDictionary.SolutionDirectory.SolutionDirectory.clear method.
    """
    foamClearSetting = Dict({"execute flag": True, "after": None, "processor": True, "pyfoam": True, "keepLast": False, "vtk": True,
                    "keepRegular": False, "clearHistory": False, "functionObjectData": True, "additional": ["postProcessing","ArchiveDir"]},
                   iotype="in",
                   desc='Option for PyFoam.RunDictionary.SolutionDirectory.SolutionDirectory.clear method.')

    def execute(self):
        self.clearCase()
        
    def clearCase(self):
        self.foam_case.clear(after=self.foamClearSetting["after"], processor=self.foamClearSetting["processor"],
                             pyfoam=self.foamClearSetting["pyfoam"], keepLast=self.foamClearSetting["keepLast"], 
                             vtk=self.foamClearSetting["vtk"], keepRegular=self.foamClearSetting["keepRegular"], 
                             clearHistory=self.foamClearSetting["clearHistory"],
                             functionObjectData=self.foamClearSetting["functionObjectData"],
                             additional=self.foamClearSetting["additional"])
            

class FoamEditDicts(FoamBaseComponent):
    """Edit and Write the OpenFOAM dictionary file.
    """
    foamEditKeywords = Dict({}, iotype='in', desc='"key" is keyword in subDict. "value" is value in subDict. the variables in "value" is appended automatic as Float.  example) {\'0/U.boundaryField.movingWall.value\':\'"uniform (%s %s %s)" %(x1,x2,x3)\'}')
    _variables=[]
    _ParsedParameterFiles={}
    
    def __init__(self):
        """Override  for class that has default foamEditKeywords"""
        super(FoamEditDicts, self).__init__()
        
        if not self.foamEditKeywords == {}:
            self._configure_Variables()
            
    
    def _getValueNames(self,val):
        val = str(val)
        return val[val.rfind("%")+1:].translate(string.maketrans("",""),"()").split(",")
        
    def _separateDict(self,key):
        """ '0/U.boundaryField.movingWall.value' -> ("0/U","boundaryField.movingWall.value")
        """
        kl = key.split(".")
        for i in xrange(1,len(kl)):
            fpath = string.join(kl[:-i],".")
            
            if os.path.exists(os.path.join(self.foam_case.name,fpath)):
                return (fpath,string.join(kl[-i:],"."))
        self.raise_exception("'%s' was  not found." % key, RuntimeError)

    def _configure_ParsedParameterFiles(self):
        """configure dict of ParsedParameterFiles"""    
        olddfiles = self._ParsedParameterFiles.keys()
        dfiles =[]
        for key,val in self.foamEditKeywords.iteritems():
            dfile = self._separateDict(key)[0]
            dfiles = dfiles + [dfile]
            
        #remove redundant data    
        dfiles = list(set(dfiles))
        
        #append dfile list
        appendList = list(set(dfiles)-set(olddfiles))
        for key in appendList:
            keyPath=os.path.join(self.foam_case.name,key)
            if os.path.exists(keyPath):
                self._ParsedParameterFiles[str(key)]=ParsedParameterFile(keyPath) 
        
        #remove dfile list
        removeList=list(set(olddfiles) - set(dfiles))
        for key in removeList:
            del(self._ParsedParameterFiles[str(key)])
    
    
    def _configure_Variables(self):
        oldvariables=self._variables
        self._variables=[]
        for key,val in self.foamEditKeywords.iteritems():
            self._variables = self._variables + self._getValueNames(val)
            
        #remove redundant data
        self._variables=list(set(self._variables)) 
        
        #append variable list
        appendList=list(set(self._variables) - set(oldvariables))
        for key in appendList:
            self.add(key,Float(0.0, iotype="in"))
        
        #remove variable list
        removeList=list(set(oldvariables) - set(self._variables))
        for key in removeList:
            self.remove(key)
    
    def _input_trait_modified(self, obj, name, old, new):
        super(FoamEditDicts, self)._input_trait_modified(obj, name, old, new)

        if name == 'foamEditKeywords_items' or name == 'foamEditKeywords':
            self._configure_Variables() 
            #self._configure_ParsedParameterFiles()
                                
    def execute(self):
        self.editDicts()
        
    def editDicts(self):
        if self.foamEditKeywords == {}:
            return
        
        for key,val in self.foamEditKeywords.iteritems():
            #append "self." '"uniform (%s 0 0)" %(x1)'->'"uniform (%s 0 0)" %(self.x1)'
            if val.rfind("%") == -1:
                continue
            val = val[:val.rfind("%")+1] + \
                  val[val.rfind("%")+1:].replace("(","(self.").replace(",",",self.").replace(" ","")
                
            #edit ParsedParameterFile
            fdkey,sdkey = self._separateDict(key)
            sdkeylist = sdkey.split(".")
            
            if not fdkey in self._ParsedParameterFiles.keys():
                self._configure_ParsedParameterFiles()
            
            di = self._ParsedParameterFiles[str(fdkey)]
            for sd in sdkeylist[:-1]:
                di = di[sd]
                
            newkey = sdkeylist[-1]
            si = newkey.rfind("[")
            sj = newkey.rfind("]")
            if si > 0 and sj > 0:
                di[newkey[:si]][int(newkey[si+1:sj])] = eval(str(val))            
            else:
                di[newkey] = eval(str(val))

        # write     
        for pf in  self._ParsedParameterFiles.itervalues():
            pf.writeFile()   
    
class FoamRunAllrun(FoamBaseComponent,ExternalCode):
    """the Allrun is executed."""
    def execute(self):
        self.runAllrun()
        
    def runAllrun(self):
        self.command = [os.path.join(self.foam_case.name,'Allrun')]
        
        if not os.path.exists(self.command[0]):
            return
        
        cDir = os.getcwd()
        os.chdir(self.foam_case.name)
        # Execute the component
        ExternalCode.execute(self)
        os.chdir(cDir)

    
class FoamRunCommands(FoamBaseComponent,ExternalCode):
    """This class executes multi external codes like Allrun."""
    commands = List([],iotype='in')
    return_codes = List([], iotype='out', desc='Return code from the commands.')
    
    command = List(Str, desc='The command to be executed for ExternalCode.')
    return_code = Int(0, desc='Return code from the command for ExternalCode.')
    
    def execute(self):
        self.runCommands()
    
    def runCommands(self):
        if self.commands == []:
            return
            
        for command in self.commands:
            #get foam command of abs path.
            commandPath = self._check_foam_command(command)
            resource = None
            if commandPath:
                #when foam command
                bname=os.path.basename(commandPath)
                self.stdout = "%s/log.%s" %(self.foam_case.name, bname)
                self.command = shlex.split("%s -case %s" %(command, self.foam_case.name))
                if command[:6] != "mpirun":
                    resource = self.resource
                    self.resource = None
                print("%s -case %s" %(bname, self.foam_case.name))
            else:
                #no foam command
                self.command=shlex.split(command)
                resource = self.resource
                self.resource = None
                self.stdout = None
                    
            super(FoamRunCommands, self).run()
            self.return_codes.append(self.return_code)
            
            if not self.resource: self.resource = resource
           
    def _check_foam_command(self,command):
    #foam_command is in $FOAM_APPBIN or $FOAM_USER_APPBIN or same dir of icoFoam.
        commandWithOutMPI = ""
        cmdList = shlex.split(command)
        if cmdList[0] != "mpirun":
            commandWithOutMPI = cmdList[0]
        else:
            for cmd in cmdList[1:]:
                if not self._which(cmd):
                    commandWithOutMPI = cmd
                    break
        
        commandPath = self._which(commandWithOutMPI)
        if not commandPath:
             self.raise_exception("Not Found %s in %s." %(commandWithOutMPI,command), RuntimeError)
        
        commandDir = os.path.dirname(commandPath)
        if commandDir == os.environ["FOAM_USER_APPBIN"]: return commandPath
        if commandDir == os.environ["FOAM_APPBIN"]: return commandPath
        if commandDir == os.path.dirname(self._which("icoFoam")): return commandPath
        return None

class TimeLineValue(VariableTree):
    """Container of variables"""
    _allTimesValues = Array(numpy.array([[0.0,0.0]]))
    averageValue = Float(0.0, iotype="out")
    latestTimeValue = Float(0.0, iotype="out")
    maxValue = Float(0.0, iotype="out")
    minValue = Float(0.0, iotype="out")
    sumValue = Float(0.0, iotype="out")
    
    def correct(self):
        """
        update averageValue,latestTimeValue,maxValue,minValue,sumValue from allTimesValues.
        """
        self.averageValue = self._allTimesValues[:,1].mean()
        self.latestTimeValue = self._allTimesValues[-1,1]
        self.maxValue = self._allTimesValues[:,1].max()
        self.minValue = self._allTimesValues[:,1].min()
        self.sumValue = self._allTimesValues[:,1].sum()
    

class FoamGetTimeline(FoamBaseComponent):
    """OpenFOAM Timeline Getter Component with PyFoam.
       TimelineData is post data with sample command. exampe)"postprocessing/probes"
    """
    foamGetTimelineKeywords = Dict({}, iotype='in', desc='"key" is variables group. "value" is post data path and column number. the "key" is appended automatic as variables group.  example){"f1":"postProcessing/probes/0/p|1')
    _TimeLineGroups=[]
    
    def __init__(self):
        """Override  for class that has default foamGetTimelineKeywords"""
        super(FoamGetTimeline, self).__init__()
        
        if not self.foamGetTimelineKeywords == {}:
            self._configure_TimeLineGroups()
                
    
    def _configure_TimeLineGroups(self):
            oldTimeLineGroups=self._TimeLineGroups
            self._TimeLineGroups=[]
            for key,val in self.foamGetTimelineKeywords.iteritems():
                self._TimeLineGroups = self._TimeLineGroups + [key]
                
            #remove redundant data
            self._TimeLineGroups=list(set(self._TimeLineGroups)) 
            
            #append TimeLineGroups list
            appendList=list(set(self._TimeLineGroups) - set(oldTimeLineGroups))
            for key in appendList:
                self.add(key,VarTree(TimeLineValue(), iotype="out"))
            
            #remove TimeLineGroups list
            removeList=list(set(oldTimeLineGroups) - set(self._TimeLineGroups))
            for key in removeList:
                self.remove(key)

    
    def _input_trait_modified(self, obj, name, old, new):
        super(FoamGetTimeline, self)._input_trait_modified(obj, name, old, new)

        if name == 'foamGetTimelineKeywords_items' or name == 'foamGetTimelineKeywords':
            self._configure_TimeLineGroups()
            
    def execute(self):
        self.getTimeline()
        
    def getTimeline(self):
        if self.foamGetTimelineKeywords == {}:
            return
        
        timeLines={} 
        
        for key,val in self.foamGetTimelineKeywords.iteritems():
            probefile,column = val.split("|",1)
            
            #from GUI get unicode but str
            probefile = str(probefile) 
            column = int(column)
            
            fieldName = os.path.basename(probefile)
            probeDir = os.path.dirname(os.path.dirname(probefile))
            wTime = float(os.path.basename(os.path.dirname(probefile)))
            
            if not timeLines.has_key(probefile):
                
                tld=TimelineDirectory(self.foam_case.name,dirName=probeDir,writeTime=wTime)
                ssdata=tld[fieldName].__call__()
                timeLines[probefile]=numpy.array(ssdata.data.tolist())
             
            res = self.get(key)
            res._allTimesValues = numpy.c_[timeLines[probefile][:,0],timeLines[probefile][:,column]]
            res.correct()


class FoamAnalyzeLogs(FoamBaseComponent):
    """OpenFOAM Log Analyzer Component with PyFoam
    """
    foamAnalyzedKeywords = Dict({}, iotype='in', desc='"key" is variables group. "value" is logfile name and string picked from log. the "key" is appended automatic as variables group.  example){"f1":"log.simpleFoam|DICPCG:  Solving for p, Initial residual = (.+?),"}')
    _ExprGroups=[]

    def __init__(self):
        """Override  for class that has default foamAnalyzedKeywords"""
        super(FoamAnalyzeLogs, self).__init__()
        
        if not self.foamAnalyzedKeywords == {}:
            self._configure_ExprGroups()

    def _configure_ExprGroups(self):
        oldExprGroups = self._ExprGroups
        self._ExprGroups = []
        for key,val in self.foamAnalyzedKeywords.iteritems():
            self._ExprGroups = self._ExprGroups + [key]
            
        #remove redundant data
        self._ExprGroups=list(set(self._ExprGroups)) 
        
        #append ExprGroups list
        appendList = list(set(self._ExprGroups) - set(oldExprGroups))
        for key in appendList:
            self.add_trait(key,VarTree(TimeLineValue(), iotype="out"))
        
        #remove ExprGroups list
        removeList=list(set(oldExprGroups) - set(self._ExprGroups))
        for key in removeList:
            self.remove_trait(key)
        

    def _input_trait_modified(self, obj, name, old, new):
        super(FoamAnalyzeLogs, self)._input_trait_modified(obj, name, old, new)

        if name == 'foamAnalyzedKeywords_items' or name == 'foamAnalyzedKeywords':
            self._configure_ExprGroups()
            
    def execute(self):
        self.analyzeLogs()
    
    def analyzeLogs(self):
        if self.foamAnalyzedKeywords == {}:
            return
            
        lineAnalyzers={} #key is variable's name. value is GeneralSimpleLineAnalyzer
        FoamLogAnalyzers={} #key is logname. value is FoamLogAnalyzer
        
        # create FoamLogAnalyzers and set lineAnalyzer each FoamLogAnalyzer loop
        for key,val in self.foamAnalyzedKeywords.iteritems():
            logname,expt = val.split("|",1)
            lineAnalyzers[key] =  GeneralSimpleLineAnalyzer(key, expt, doFiles=False)  
            if not FoamLogAnalyzers.has_key(logname):
                FoamLogAnalyzers[logname] = FoamLogAnalyzer(progress=True)
            FoamLogAnalyzers[logname].addAnalyzer(key, lineAnalyzers[key])

        # LogAnalyzerApplication run            
        for logname, val in FoamLogAnalyzers.iteritems():
            log_app = LogAnalyzerApplication(val)
            log_app.run(os.path.join(self.foam_case.name,logname))

        # get result from  lineAnalyzer     
        for key,val in lineAnalyzers.iteritems():
            res = self.get(key)
            res._allTimesValues = numpy.array(list(val.getTimeline(key + '_0'))).transpose()
            res.correct()


class OpenFOAM_wrapper(FoamClearCase, FoamEditDicts, FoamRunAllrun, FoamGetTimeline, FoamAnalyzeLogs):
    """
    The simple operation inherited five component classes.
        * FoamClearCase
        * FoamEditDicts
        * FoamRunAllrun
        * FoamGetTimeline
        * FoamAnalyzeLogs
    
    """
    def _input_trait_modified(self, obj, name, old, new):
        """hook th changing a trait."""
        super(OpenFOAM_wrapper, self)._input_trait_modified(obj, name, old, new)
            
    def execute(self):
        """
        It is executed in the order of the following.
            1. clear Case
            2. Edit Dict
            3. execute Allrun
            4. get timeLines. (probes etc)    
            5. log Analysis
               
        """
        FoamClearCase.execute(self)  
        FoamEditDicts.execute(self)
        FoamRunAllrun.execute(self)
        FoamGetTimeline.execute(self)
        FoamAnalyzeLogs.execute(self)
        
