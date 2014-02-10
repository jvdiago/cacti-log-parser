#!/usr/bin/env python

import os, sys, time
from daemon import Daemon
from email.mime.text import MIMEText
import re
import json
import smtplib
import logging
import logging.config
from suds.client import Client
from ConfigParser import SafeConfigParser

####### LOGGING ######
logging.config.fileConfig('/opt/cacti_log_parser/etc/logging.conf')
logger = logging.getLogger('root')
logging.getLogger('suds.client').setLevel(logging.INFO)
logging.getLogger('suds.transport').setLevel(logging.INFO)
logging.getLogger('suds.xsd.schema').setLevel(logging.INFO)
logging.getLogger('suds.wsdl').setLevel(logging.INFO)
######################

######## CONFIG ##########
CONFIG_FILE = '/opt/cacti_log_parser/etc/parser.ini'
##########################

###### GLOBALS ######
MAIN_LOOP_EXCEPTION = 1
ERR_CONFIG_FILE = 2
ITSM = 1
EMAIL = 2
#####################


class Parser(Daemon):
	def __init__(self):
		self.readConfig(CONFIG_FILE)
		Daemon.__init__(self,self.PIDFILE)
		self.alerts = {}
		self.dict_modified = 0 
		self.delay_window = 0
		self.last_notification = 0 
		self.host_name = ''

	def readConfig(self,config):
		try:
			parser = SafeConfigParser()
			parser.read(config)
			self.JSON_FILE = parser.get('main','JSON_FILE')
			self.CACTI_LOGFILE = parser.get('main','CACTI_LOGFILE')
			self.PIDFILE = parser.get('main','PIDFILE')
			self.NOTIFICATION_DELAY = parser.getint('main','NOTIFICATION_DELAY')
			self.NOTIFICATION_WINDOW = parser.getint('main','NOTIFICATION_WINDOW')
			self.TIME_BEFORE_RESET = parser.getint('main','TIME_BEFORE_RESET')
			self.NOTIFICATION_METHOD = parser.getint('main','NOTIFICATION_METHOD')
			self.SUMMARY = parser.get('main','SUMMARY')

			self.ITSM_URL = parser.get('itsm','ITSM_URL')
			self.ITSM_LOCATION = parser.get('itsm','ITSM_LOCATION')
			self.ITSM_USERNAME = parser.get('itsm','ITSM_USERNAME')
			self.ITSM_PASSWORD = parser.get('itsm','ITSM_PASSWORD')
			self.ASSIGNED_GROUP = parser.get('itsm','ASSIGNED_GROUP')
			self.ASSIGNED_SUPPORT_COMPANY = parser.get('itsm','ASSIGNED_SUPPORT_COMPANY')
			self.FIRST_NAME = parser.get('itsm','FIRST_NAME')
			self.IMPACT = parser.get('itsm','IMPACT')
			self.LAST_NAME = parser.get('itsm','LAST_NAME')
			self.REPORTED_SOURCE = parser.get('itsm','REPORTED_SOURCE')
			self.SERVICE_TYPE = parser.get('itsm','SERVICE_TYPE')
			self.STATUS = parser.get('itsm','STATUS')
			self.ACTION = parser.get('itsm','ACTION')
			self.CREATE_REQUEST = parser.get('itsm','CREATE_REQUEST')
			self.URGENCY = parser.get('itsm','URGENCY')

			self.EMAIL_TO = parser.get('email','EMAIL_TO')
			self.EMAIL_FROM = parser.get('email','EMAIL_FROM')
		except:
			logging.error('A problem ocurred when parsing the %s config file. Exception: %s %s',CONFIG_FILE,str(sys.exc_info()[0]),str(sys.exc_info()[1]))
			sys.exit(ERR_CONFIG_FILE)

	def soapCreateIncident(self,summary,notes):
		try:
			client = Client(self.ITSM_URL)
			client.options.location = self.ITSM_LOCATION

			token = client.factory.create('AuthenticationInfo')
			token.userName = self.ITSM_USERNAME
			token.password = self.ITSM_PASSWORD
			client.set_options(soapheaders=token)

			result = client.service.HelpDesk_Submit_Service(
			Assigned_Group=self.ASSIGNED_GROUP,
			Assigned_Support_Company=self.ASSIGNED_SUPPORT_COMPANY,
			First_Name=self.FIRST_NAME,
			Impact=self.IMPACT,
			Last_Name=self.LAST_NAME,
			Reported_Source=self.REPORTED_SOURCE,
			Service_Type=self.SERVICE_TYPE,
			Status=self.STATUS,
			Action=self.ACTION,
			Create_Request=self.CREATE_REQUEST,
			Summary=summary,
			Notes=notes,
			Urgency=self.URGENCY)
			logging.info('ITSM Incident created. INC %s. Summary %s. Notes %s',result,summary,notes)
			return 0
		except:
			logging.error('A problem ocurred when creating an Incident in ITSM. Message: %s %s. Exception: %s %s',summary,notes,str(sys.exc_info()[0]),str(sys.exc_info()[1]))
			return 1

	def follow(self,thefile):
	    thefile.seek(0,2)      # Go to the end of the file
	    while True:
		 line = thefile.readline()
		 if not line:
		     time.sleep(0.1)    # Sleep briefly
		     continue
		 yield line

	def storeDict(self):
		if self.dict_modified == 1:
			try:
				with open(self.JSON_FILE,'w+') as fp:
					json.dump(self.alerts,fp)
				self.dict_modified = 0
				logging.debug('Alerts dictionary dumped to %s',self.JSON_FILE)
			except:
				logging.error('A problem ocurred when dumping the self.alerts dictionary to %s. %s %s',self.JSON_FILE,str(sys.exc_info()[0]),str(sys.exc_info()[1]))
				pass
			

	def loadDict(self):
		try:
			with open(self.JSON_FILE,'r') as fp:
				self.alerts = json.load(fp)
		except:
			logging.error('A problem ocurred when loading the alerts from %s. %s %s',self.JSON_FILE,str(sys.exc_info()[0]),str(sys.exc_info()[1]))
			self.alerts = {}

	def sendMail(self,to, fromEmail, subject, body):
		msg = MIMEText(body)

		msg['Subject'] = subject 
		msg['From'] = fromEmail
		msg['To'] = to

		try:
			s = smtplib.SMTP('localhost')
			s.sendmail(fromEmail, [to], msg.as_string())
			s.quit()

			logging.info('Email sent to %s: %s',to,body)
		except:
			logging.error('A problem ocurred when sending an email to %s. Message: %s Exception: %s %s',to,body,str(sys.exc_info()[0]),str(sys.exc_info()[1]))
			
		
		return 0

	#WARNING: SNMP Get Timeout for Host:'ICCMGM001-LIN'
	def parseLine(self,line):
		try:
			m = re.search(r"(?P<time>.*)WARNING: SNMP Get Timeout for Host:'(?P<host_name>.*)',(?P<rest>.*)",line)
			self.host_name = m.group('host_name')
		except:
			self.host_name = ''

		logging.debug('Hostname: %s',self.host_name)

	def storeHost(self):
		if self.host_name != '':
			if not self.alerts.has_key(self.host_name):
				self.alerts[self.host_name] = 0
				self.dict_modified = 1

	def createNotification(self):
		notify = 0
		message = ['The next Hosts have problems in Cacti:\n'] 
		now = int(time.time())
		for host in self.alerts.keys():
			if self.alerts[host] == 0:
				message.append(host)
				message.append('\n')	
				self.alerts[host] = now
				notify = 1
				self.dict_modified = 1 

		if notify == 1:
			return ''.join(message)	
		else:
			return ''

	def notifyHosts(self):
		now = int(time.time())
		time_diff = now - self.last_notification
		if time_diff >  self.NOTIFICATION_DELAY:
			if self.delay_window == 0 and self.host_name != '': #Waits NOTIFICATION_WINDOW more seconds before sending an alert even if NOTIFICATION_DELAY treshold has been exceded (to catch bursts)
				self.last_notification = now - self.NOTIFICATION_DELAY + self.NOTIFICATION_WINDOW
				self.delay_window = 1
			else:
				self.delay_window = 0
				message = self.createNotification()
				if message != '':
					if self.NOTIFICATION_METHOD == ITSM:
						error = self.soapCreateIncident(self.SUMMARY,message) 
					else:
						error = self.sendMail(self.EMAIL_TO,self.EMAIL_FROM,self.SUMMARY,message)	
					if error == 0:
						self.last_notification = now
						logging.debug('Changing the self.last_notification to: %i',self.last_notification) 

	def resetHosts(self):
		for host,notify in self.alerts.items():
			if notify > 0: 
				now = int(time.time())
				diff = now - notify
				if diff >= self.TIME_BEFORE_RESET:
					del self.alerts[host]
					self.dict_modified = 1	
					logging.debug('Deleting host from the dictionary: %s',host)

	def run(self):
		try:
			self.loadDict()
			self.last_notification = int(time.time())
			logfile = open(self.CACTI_LOGFILE)
			loglines = self.follow(logfile)
			for line in loglines:
				self.parseLine(line)
				self.storeHost()
				self.notifyHosts()
				self.resetHosts()
				self.storeDict()
		except:
			logging.error("Exception on main loop. Exception: %s %s",str(sys.exc_info()[0]),str(sys.exc_info()[1]))
			sys.exit(MAIN_LOOP_EXCEPTION)
		

if __name__ == "__main__":
	parser = Parser()
	if len(sys.argv) == 2:
		if 'start' == sys.argv[1]:
			parser.start()
		elif 'stop' == sys.argv[1]:
			parser.stop()
		elif 'restart' == sys.argv[1]:
			parser.restart()
		else:
			print "Unknown command"
			sys.exit(2)
		sys.exit(0)
	else:
		print "usage: %s start|stop|restart" % sys.argv[0]
		sys.exit(2)
