#!/usr/bin/python

"""
Searchs PyPi for modules corresponding to term provided, downloads, unzips, and untars them. 
Returns path to unzipped, untarred module.

"""


import argparse
import datetime
import glob
import hashlib
import os
import plistlib
import re
import sys
import subprocess
import tarfile
import urllib, urllib2
from Foundation import NSUserName

installcheck_script = """#!/usr/bin/python
try:
	import sys, MODULE
except ImportError:
	print "MODULE not found, needs to be installed"
	sys.exit(0)
path = MODULE.__path__[0]
version = path.split('site-packages/')[1].split('-')[1]
exit_value = version >= 'VERS'
print "Found MODULE with version %s" % (version)
if exit_value == 0:
	print "Installing version VERS"
else:
	print "Installed version up-to-date"
sys.exit(exit_value)""".encode('ascii', 'xmlcharrefreplace')

postinstall_script = """#!/bin/bash
logdir="LOGDIR"
if [ ! -d "$logdir" ]; then
	mkdir -p "$logdir"
fi
cd SETUP_DIR
python setup.py install --record "$logdir/installs.txt"
exit $?""".encode('ascii', 'xmlcharrefreplace')

uninstall_script = """#!/bin/bash
logdir="LOGDIR"
xargs rm -v < "$logdir/installs.txt"
rm "$logdir/installs.txt"
exit $?""".encode('ascii', 'xmlcharrefreplace')

def getModule(module):
	pypi_url = "https://pypi.python.org"
	pypi_path = "%s/pypi/%s" % (pypi_url, module)
	index_regex = r'Index of Packages'
	module_regex = r'/pypi/' + module + '/(\d+\.)+(\d+)'
	source_regex = r'https://pypi.python.org/packages/source/.+tar\.gz#md5=[^"]+'
	# If page is an "Index of Packages" page then find the url for the page for the most recent version
	isIndex = getMatch(pypi_path, index_regex)
	if isIndex:
		new_path = getMatch(pypi_path, module_regex)
		pypi_path = pypi_url + new_path
	# Get url to the tarred, zipped source file
	source_url = getMatch(pypi_path, source_regex)
	# If source url cannot be found skip the module
	if not source_url:
		print "%s not found on PyPi. Ensure the module name is spelled correctly." % module
		return None
	if not os.path.exists(module):
		os.makedirs(module)
	# Creates path to file where zip will be downloaded
	zip_file = source_url.split('/')[-1].split('#')[0]
	zip_path = module + "/" + zip_file
	module_name = zip_file.split('.tar.gz')[0]
	# Downloads zip
	urllib.urlretrieve(source_url, zip_path)
	# Preps module tar.gz file to be extracted
	tfile = tarfile.open(zip_path, 'r:gz')
	# Extracts contents of module tar.gz to directory for module
	tfile.extractall(module + "/" + module_name + "/")
	# Gets the modules root directory from the recently extracted contents
	module_dir = min(glob.iglob(module + "/*"), key=os.path.getctime)
	tfile.close()
	return module_dir

# Searchs html at specified URL for matches to given regex pattern.
# Returns first match if found, nothing otherwise.
def getMatch(url, regex):
	# Tries to open URL for reading. If url doesn't exist raises exception.
	try:
		f = urllib2.urlopen(url)
	except:
		return ""
	# If url open successful reads contents of html into string html
	html = f.read()
	pattern = re.compile(regex)
	match = pattern.search(html)
	if match:
		return match.group(0)
	else:
		return ""

# Returns True if PKG-INFO exists, False otherwise
def hasPkgInfo(pkginfo_path):
	return os.path.exists(pkginfo_path)

# Returns Name, Version, Summary, Author in dictionary format
def getPkgInfo(module_dir):
	# Specify which pkginfo get key / value pairs for from the PKG-INFO file
	keys = ('Name', 'Version', 'Summary', 'Author')
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
	tmp_path = "/tmp"
	# Path to directory for install log needed for uninstallation
	log_dir = "/Library/Application Support/Managed Python/" + dmg_name
	# Get path to directory holding files for this tool
	tool_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
	# Path to plist file pkginfo keys are written to
	pkginfo_path = os.getcwd() + "/" + dmg_name + ".pkginfo"
	# Path to setup.py within module tmp directory
	setup_path = tmp_path + "/" + dmg_name
	pkginfo = dict(
		_metadata=dict(
			created_by=NSUserName(),
			creation_date=datetime.datetime.utcnow(),
			os_version=subprocess.check_output(['sw_vers', '-productVersion']).rstrip('\n'),
		),
		autoremove=False,
		catalogs=list(['testing']),
		description=description,
		installcheck_script=installcheck_script.replace("MODULE", name).replace("VERS", version),
		installer_item_hash=hashlib.sha256(open(dmg_path, 'rb').read()).hexdigest(),
		installer_item_location=dmg,
		installer_item_size=int(os.path.getsize(dmg_path) / 1024),
		installer_type='copy_from_dmg',
		items_to_copy=list((
			dict(
				destination_path=tmp_path,
				source_item=dmg_name,
			),
		)),
		minimum_os_version='10.4.0',
		name=name,
		postinstall_script=postinstall_script.replace("LOGDIR", log_dir).replace("SETUP_DIR", setup_path),
		requires=list(['XcodeTools']),
		unattended_install=True,
		unattended_uninstall=True,
		uninstall_method='uninstall_script',
		uninstall_script=uninstall_script.replace("LOGDIR", log_dir),
		uninstallable=True,
		version=version,
	)
	plistlib.writePlist(pkginfo, pkginfo_path)
	return pkginfo_path

# DO NOT IMPLEMENT YET. POSSIBLY MOVE TO AUTOPKG
# Imports pkginfo and DMG into munki repository
def importModule():
	pass

def main():
	parser = argparse.ArgumentParser(description='Command line tool to fetch PyPi module sources and package them for Munki deployement')
	parser.add_argument('module', metavar='module', type=str, nargs='+', help='name of a PyPi module')
	args = parser.parse_args()
	modules = args.module
	for module in modules:
		module_dir = getModule(module)
		if module_dir is None:
			print "Skipping %s" % (module)
			continue
		if hasPkgInfo(module_dir):
			extracted_info = getPkgInfo(module_dir)
		else: 
			print "Could not find PKG-INFO for specified module"
			exit(1)
		print extracted_info # Used for debugging
		dmg = makeDMG(module_dir)
		makePkgInfo(dmg, extracted_info)

if __name__ == "__main__":
    main()
