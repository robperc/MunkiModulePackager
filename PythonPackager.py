import datetime
import glob
import hashlib
import inspect
import os
import plistlib
import re
import sys
import subprocess
import tarfile
import urllib, urllib2
from Foundation import NSDate, NSUserName

# Searchs PyPi for modules corresponding to term provided, downloads, unzips, and untars them. 
# Returns path to unzipped, untarred module
# URL: https://pypi.python.org/packages/source/MODULE[0]/MODULE/MODULE-x.x.x.tar.gz#md5=SOME_HASH_STRING

def getModule(module):
	# Tries to open module URL for reading. If module spelled wrong or doesn't exist on PyPi raises exception.
	try:
		pypi_url = "https://pypi.python.org/pypi/" + module
		f = urllib2.urlopen(pypi_url)
	except BaseException as e:
		print "Error while searching PyPi for %s: %s" % (module, e)
	# If url open successful reads contents of html into string html
	html = f.read()
	regex = r'https://pypi.python.org/packages/source/.+tar\.gz#md5=[^"]+'
	tar_gz = re.compile(regex)
	module_url = tar_gz.search(html).group(0)
	if not module_url:
		raise ProcessorError("Couldn't find %s source download on PyPi" % (module))
	# If the directory for the module doesn't already exist create it.
	if not os.path.exists(module):
		os.makedirs(module)
	# Creates path to file where zip will be downloaded
	zip_file = module_url.split('/')[-1].split('#')[0]
	zip_path = module + "/" + zip_file
	module_name = zip_file.split('.tar.gz')[0]
	# Downloads zip
	urllib.urlretrieve(module_url, zip_path)
	# Preps module tar.gz file to be extracted
	tfile = tarfile.open(zip_path, 'r:gz')
	# Extracts contents of module tar.gz to directory for module
	tfile.extractall(module + "/" + module_name + "/")
	# Gets the modules root directory from the recently extracted contents
	module_dir = min(glob.iglob(module + "/*"), key=os.path.getctime)
	tfile.close()
	return module_dir

# Returns True if PKG-INFO exists, False otherwise
def hasPkgInfo(pkginfo_path):
	return os.path.exists(pkginfo_path)

# Returns Name, Version, Summary, Author in dictionary format
def getPkgInfo(module_dir):
	# Specify which pkginfo get key / value pairs for from the PKG-INFO file
	keys = ['Name', 'Version', 'Summary', 'Author']
	module_pkginfo = module_dir + '/' + module_dir.split('/')[-1] + '/PKG-INFO'
	# Extract the lines from the PKG-INFO into a list
	lines = [line.rstrip('\n') for line in open(module_pkginfo)]
	# Get the specified key / value pairs from the list of lines in dictionary form
	pkginfo = {line.split(':')[0]: line.split(':')[1].strip(' ') for line in lines if line.split(':')[0] in keys}
	return pkginfo

# Creates DMG containing python module. Returns path to DMG
def makeDMG(module_dir):
	# Get portion of module path that specifies name and version
	name_vers = module_dir.split('/')[-1]
	# Prep bash command string to create module dmg
	mk_dmg_args = "hdiutil create -volname " + name_vers + " -srcfolder " + module_dir + " -ov -format UDZO " + name_vers + ".dmg"
	# Try to create DMG, print error if exception occurs
	try:
		subprocess.check_call(mk_dmg_args.split())
	except Exception as e:
		print "An error occured during creation of DMG for module: %s" % (e)
	# Return path to the newly created DMG
	return os.getcwd() + "/" + name_vers + ".dmg"

# Creates a custom pkginfo for python module. Returns path to pkginfo
def makePkgInfo(dmg_path, info):
	# Info from PKG-INFO
	name = info['Name']
	version = info['Version']
	description = info['Summary']
	# Local path to dmg
	dmg = dmg_path.split('/')[-1]
	# Filename of dmg with file extension removed
	dmg_name = dmg.split('.dmg')[0]
	# Path to temp location of install files
	tmp_path = "/tmp/" + dmg_name
	# Path to directory for install log needed for uninstallation
	log_dir = "/Library/Application Support/Managed Python/" + dmg_name
	# Get path to directory holding files for this tool
	tool_dir = '/'.join(inspect.stack()[0][1].split('/')[0:-1])
	# Path to plist file pkginfo keys are written to
	pkginfo_path = os.getcwd() + "/" + dmg_name + ".pkginfo"

	# Prep installcheck script for pkginfo
	installcheck_script = """#!/usr/bin/python
try:
	import sys, MODULE
except ImportError:
	print "MODULE not found, needs to be installed"
	sys.exit(0)
exit_value = MODULE.__version__.rstrip('\\n') >= 'VERS'
sys.exit(exit_value)""".replace("MODULE", name).replace("VERS", version)

	# Prep postinstall script for pkginfo
	postinstall_script = """#!/bin/bash
logdir="LOGDIR"
if [ ! -d "$logdir" ]; then
	mkdir -p "$logdir"
fi
python SETUP_FILE install --record "$logdir/installs.txt"
exit $?""".replace("LOGDIR", log_dir)

	# Prep uninstall script for pkginfo
	uninstall_script = """#!/bin/bash
logdir="LOGDIR"
xargs rm -v < "$logdir/installs.txt"
exit $?""".replace("LOGDIR", log_dir)

	# Parse pkginfo template into dictionary
	pkginfo = plistlib.readPlist(tool_dir + '/template')
	# Set values from pkginfo template
	pkginfo['_metadata']['created_by'] = NSUserName()
	pkginfo['_metadata']['creation_date'] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
	pkginfo['_metadata']['os_version'] = subprocess.check_output(['sw_vers', '-productVersion']).rstrip('\n')
	pkginfo['description'] = description
	pkginfo['installcheck_script'] = installcheck_script.encode('ascii', 'xmlcharrefreplace')
	pkginfo['installer_item_hash'] = hashlib.sha256(open(dmg_path, 'rb').read()).hexdigest()
	pkginfo['installer_item_location'] = dmg
	pkginfo['installer_item_size'] = int(os.path.getsize(dmg_path) / 1024)
	pkginfo['items_to_copy'][0]['destination_path'] = tmp_path
	pkginfo['items_to_copy'][0]['source_item'] = dmg_name
	pkginfo['name'] = name
	pkginfo['postinstall_script'] = postinstall_script.encode('ascii', 'xmlcharrefreplace')
	pkginfo['uninstall_script'] = uninstall_script.encode('ascii', 'xmlcharrefreplace')
	pkginfo['version'] = version
	plistlib.writePlist(pkginfo, pkginfo_path)
	return pkginfo_path

# Imports pkginfo and DMG into munki repository
# DO NOT IMPLEMENT YET. POSSIBLY MOVE TO AUTOPKG
def importModule():
	pass


module_dir = getModule("mac_alias")
print module_dir
if hasPkgInfo(module_dir):
	extracted_info = getPkgInfo(module_dir)
else: 
	print "Could not find PKG-INFO for specified module"
	exit(1)
print extracted_info
dmg = makeDMG(module_dir)
makePkgInfo(dmg, extracted_info)