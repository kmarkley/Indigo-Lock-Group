#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# http://www.indigodomo.com

import indigo
import time
from ghpu import GitHubPluginUpdater

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.

###############################################################################
# globals

k_updateCheckHours = 24

################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.updater = GitHubPluginUpdater(self)

    def __del__(self):
        indigo.PluginBase.__del__(self)

    #-------------------------------------------------------------------------------
    # Start, Stop and Config changes
    #-------------------------------------------------------------------------------
    def startup(self):
        self.nextCheck = self.pluginPrefs.get('nextUpdateCheck',0)
        self.debug = self.pluginPrefs.get('showDebugInfo',False)
        self.logger.debug("startup")
        if self.debug:
            self.logger.debug("Debug logging enabled")
        self.deviceDict = dict()
        indigo.devices.subscribeToChanges()

    #-------------------------------------------------------------------------------
    def shutdown(self):
        self.logger.debug("shutdown")
        self.pluginPrefs['nextUpdateCheck'] = self.nextCheck
        self.pluginPrefs['showDebugInfo'] = self.debug

    #-------------------------------------------------------------------------------
    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.logger.debug("closedPrefsConfigUi")
        if not userCancelled:
            self.debug = valuesDict.get("showDebugInfo",False)
            if self.debug:
                self.logger.debug("Debug logging enabled")

    #-------------------------------------------------------------------------------
    def runConcurrentThread(self):
        self.logger.debug("runConcurrentThread")
        try:
            while True:
                if time.time() > self.nextCheck:
                    self.checkForUpdates()
                self.sleep(600)
        except self.StopThread:
            pass    # Optionally catch the StopThread exception and do any needed cleanup.

    #-------------------------------------------------------------------------------
    # Device Methods
    #-------------------------------------------------------------------------------
    def deviceStartComm(self, device):
        self.logger.debug("deviceStartComm: "+device.name)

        if device.version != self.pluginVersion:
            self.updateDeviceVersion(device)

        if device.configured:
            self.deviceDict[device.id] = self.LockGroup(device, self.logger)

    #-------------------------------------------------------------------------------
    def deviceStopComm(self, device):
        self.logger.debug("deviceStopComm: "+device.name)
        if device.id in self.deviceDict:
            del self.deviceDict[device.id]

    #-------------------------------------------------------------------------------
    def validateDeviceConfigUi(self, valuesDict, typeId, devId, runtime=False):
        self.logger.debug("validateDeviceConfigUi: " + typeId)
        errorsDict = indigo.Dict()

        if not valuesDict.get('locks',''):
            errorsDict['locks'] = "Select at least one lock"

        if len(errorsDict) > 0:
            return (False, valuesDict, errorsDict)
        else:
            return (True, valuesDict)

    #-------------------------------------------------------------------------------
    def updateDeviceVersion(self, device):
        theProps = device.pluginProps
        # update states
        device.stateListOrDisplayStateIdChanged()
        # check for changed props

        # push to server
        theProps["version"] = self.pluginVersion
        device.replacePluginPropsOnServer(theProps)


    #-------------------------------------------------------------------------------
    # Device updated
    #-------------------------------------------------------------------------------
    def deviceUpdated(self, oldDev, newDev):

        # device belongs to plugin
        if newDev.pluginId == self.pluginId or oldDev.pluginId == self.pluginId:
            # update local copy (will be removed/overwritten if communication is stopped/re-started)
            indigo.PluginBase.deviceUpdated(self, oldDev, newDev)
            if newDev.id in self.deviceDict:
                self.deviceDict[newDev.id].refresh(newDev)

        # speedcontrol device
        elif isinstance(newDev, indigo.RelayDevice):
            for devId, device in self.deviceDict.items():
                device.lockUpdated(oldDev, newDev)

    #-------------------------------------------------------------------------------
    # Action Methods
    #-------------------------------------------------------------------------------
    def actionControlDimmerRelay(self, action, device):
        self.logger.debug("actionControlDimmerRelay: "+device.name)
        lockGroup = self.deviceDict[device.id]
        # LOCK
        if action.deviceAction == indigo.kDeviceAction.Lock:
            lockGroup.lock()
        # UNLOCK
        elif action.deviceAction == indigo.kDeviceAction.Unlock:
            lockGroup.unlock()
        # TOGGLE
        elif action.deviceAction == indigo.kSpeedControlAction.Toggle:
            lockGroup.toggle()
        # STATUS REQUEST
        elif action.deviceAction == indigo.kUniversalAction.RequestStatus:
            self.logger.info('"{}" status update'.format(device.name))
            lockGroup.updateGroup()
        # UNKNOWN
        else:
            self.logger.debug('"{}" {} request ignored'.format(dev.name, unicode(action.speedControlAction)))

    #-------------------------------------------------------------------------------
    # Menu Methods
    #-------------------------------------------------------------------------------
    def checkForUpdates(self):
        try:
            self.updater.checkForUpdate()
        except Exception as e:
            msg = 'Check for update error.  Next attempt in {} hours.'.format(k_updateCheckHours)
            if self.debug:
                self.logger.exception(msg)
            else:
                self.logger.error(msg)
                self.logger.debug(e)
        self.nextCheck = time.time() + k_updateCheckHours*60*60

    #-------------------------------------------------------------------------------
    def updatePlugin(self):
        self.updater.update()

    #-------------------------------------------------------------------------------
    def forceUpdate(self):
        self.updater.update(currentVersion='0.0.0')

    #-------------------------------------------------------------------------------
    def toggleDebug(self):
        if self.debug:
            self.logger.debug("Debug logging disabled")
            self.debug = False
        else:
            self.debug = True
            self.logger.debug("Debug logging enabled")

    #-------------------------------------------------------------------------------
    # Menu Callbacks
    #-------------------------------------------------------------------------------
    def getLockDeviceList(self, filter="", valuesDict=None, typeId="", targetId=0):
        excludeList  = [dev.id for dev in indigo.devices.iter(filter='self')]
        return [(dev.id, dev.name) for dev in indigo.devices.iter(filter='indigo.relay, props.IsLockSubType') if (dev.id not in excludeList)]


    ###############################################################################
    # Classes
    ###############################################################################
    class LockGroup(object):

        #-------------------------------------------------------------------------------
        def __init__(self, device, logger):
            self.logger = logger
            self.logger.debug("LockGroup.__init__: {}".format(device.id))

            self.id = device.id
            self.refresh(device)

            self.lockDict = dict()
            for lockId in self.props.get('locks',[]):
                self.lockDict[int(lockId)] = indigo.devices[int(lockId)]

            self.updateGroup()

        #-------------------------------------------------------------------------------
        # action methods
        #-------------------------------------------------------------------------------
        def lock(self):
            self.logger.info('"{}" lock'.format(self.name))
            for lockId, lock in self.lockDict.items():
                indigo.device.lock(lockId)

        #-------------------------------------------------------------------------------
        def unlock(self):
            self.logger.info('"{}" unlock'.format(self.name))
            for lockId, lock in self.lockDict.items():
                indigo.device.unlock(lockId)

        #-------------------------------------------------------------------------------
        def toggle(self):
            if self.onState:
                self.unlock()
            else:
                self.lock()

        #-------------------------------------------------------------------------------
        # device updated methods
        #-------------------------------------------------------------------------------
        def refresh(self, device=None):
            if not device:
                device  = indigo.devices[self.id]
            self.logger.debug("LockGroup.refresh: {}".format(device.name))
            self.device = device
            self.name   = device.name
            self.props  = device.pluginProps
            self.states = device.states

        #-------------------------------------------------------------------------------
        def lockUpdated(self, oldDev, newDev):
            if newDev.id in self.lockDict:
                self.logger.debug("LockGroup.lockUpdated: {} ({})".format(self.name, newDev.name))
                self.lockDict[newDev.id] = indigo.devices[newDev.id]
                self.updateGroup()

        #-------------------------------------------------------------------------------
        def updateGroup(self):
            self.logger.debug("LockGroup.updateGroup: {}".format(self.name))
            self.states['anyLocked'] = any(lock.onState for lock in self.lockDict.values())
            self.states['allLocked'] = all(lock.onState for lock in self.lockDict.values())
            self.states['numLocked'] = sum(lock.onState for lock in self.lockDict.values())
            if self.props['statusLogic'] == 'all':
                self.states['onOffState'] = self.states['allLocked']
            else:
                self.states['onOffState'] = self.states['anyLocked']
            
            if self.states != self.device.states:
                newStates = []
                for key, value in self.states.items():
                    if self.device.states[key] != value:
                        self.logger.debug('{}:{}'.format(key,value))
                        newStates.append({'key':key,'value':value})
                self.device.updateStatesOnServer(newStates)
