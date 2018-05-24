
import sys
import requests
import csv
import json
from dateutil import parser as dp
from collections import Counter
from time import sleep
from math import ceil as ceil
from datetime import datetime, timezone
from dateutil import parser as dp
import os

org_slug = ''
users_final = {}
user_count = 0
homedir = os.environ['HOME']

org = str(input("\nEnter org slug: "))
while len(org) < 1:
	org = str(input("You must enter an organization: "))

org_api_id = str(input("\nEnter org API ID: "))
while len(org_api_id) != 8:
	org_api_id = input("Invalid API ID. (Should be 8 digits in length) Try again: ")

org_api_key = str(input("\nEnter org API Key: "))
while len(org_api_key) != 32:
	org_api_key = input("Invalid API key. (Should be 32 digits in length) Try again: ")


#-------------------------------------------------------------------------------------------------------------
# Build http request headers from user input.
org_headers = {
	'Content-type':'application/json',
	'X-VO-Api-Id': org_api_id,
	'X-VO-Api-Key': org_api_key,
}

#-------------------------------------------------------------------------------------------------------------
# Get list of users

def getUsers():
	"""Get all users info from VO API"""

	global users_final
	global user_count

	users_request = requests.get('https://api.victorops.com/api-public/v1/user', headers = org_headers)

	# Convert the json response to a Python dictionary
	users_dict = json.loads(users_request.text)

	# Get a count of the users in the response
	user_count = str(users_dict).count('username')

	# Create a clean, nested Python dictionary for all users.
	for x in range(0,user_count):
		# Check if key "email" exists for user and assign a value of "None" if it does not
		if 'email' in users_dict['users'][0][x]:
			username = (users_dict['users'][0][x]['username'])
			firstName = (users_dict['users'][0][x]['firstName'])
			lastName = (users_dict['users'][0][x]['lastName'])
			email = (users_dict['users'][0][x]['email'])
			createdDate = (users_dict['users'][0][x]['createdAt'])
			verified = (users_dict['users'][0][x]['verified'])
			passwordLastUpdated = (users_dict['users'][0][x]['passwordLastUpdated'])
		else:
			username = (users_dict['users'][0][x]['username'])
			firstName = (users_dict['users'][0][x]['firstName'])
			lastName = (users_dict['users'][0][x]['lastName'])
			email = 'None'
			createdDate = (users_dict['users'][0][x]['createdAt'])
			verified = (users_dict['users'][0][x]['verified'])
			passwordLastUpdated = (users_dict['users'][0][x]['passwordLastUpdated'])

		# Handle unverified users in invited state
		if 'invited_' in username:
			users_final[username] = {}
			users_final[username]['firstName'] = 'None'
			users_final[username]['lastName'] = 'None'
			users_final[username]['email'] = str(email)
			users_final[username]['createdDate'] = str(createdDate)
			users_final[username]['verified'] = verified
			users_final[username]['passwordLastUpdated'] = str(passwordLastUpdated)
		else:
			users_final[username] = {}
			users_final[username]['firstName'] = str(firstName)
			users_final[username]['lastName'] = str(lastName)
			users_final[username]['email'] = str(email)
			users_final[username]['createdDate'] = str(createdDate)
			users_final[username]['verified'] = verified
			users_final[username]['passwordLastUpdated'] = str(passwordLastUpdated)

	return users_final, user_count


#-------------------------------------------------------------------------------------------------------------
# Audit last time password was updated for each user and add it to users_final

def auditPasswordUpdate():
	global users_final
	users_list = users_final.keys()
	for user in users_list:
		last_update = dp.parse(users_final[user]['passwordLastUpdated'])
		diff = datetime.now(timezone.utc) - last_update
		users_final[user]['password_age_days'] = diff.days

	return users_final, user_count

#-------------------------------------------------------------------------------------------------------------
# Get each users paging policy

def getPagingPolicies():
	# Access the returns from getUsers()
	global users_final
	global user_count

	# Estimate how long it will take to fetch paging policies given the rate
	estimated_time = ceil((user_count * 5) / 60)
	print("--------------------------------------------------------\nGetting paging policies for %s users.\n\nApproximate time to complete: %s minutes\n--------------------------------------------------------" % (user_count, estimated_time))

	# Extract a list of usernames
	users_list = sorted(users_final.keys())
	# Iterate through list of users, polling the API for each user's personal paging policy

	count = 0

	for user in users_list:
		request_url = str('https://api.victorops.com/api-public/v1/user/%s/policies' % (user))

		policies_request = requests.get(request_url, headers = org_headers)

		# Convert the JSON response to a Python dictionary
		policies_dict = json.loads(policies_request.text)

		# Extract 'order' field as a Python list
		steps = [x['order'] for x in policies_dict['policies']]

		# #Extract 'contactType' as a list
		contactMethods = [x['contactType'] for x in policies_dict['policies']]

		# Extract 'timeout' field as a Python list
		timeouts = [x['timeout'] for x in policies_dict['policies']]

		# Convert paging policy to a simple Python dict
		pagingPolicy = {}

		if len (steps) == 1:
			pagingPolicy['step1'] = str(contactMethods[0])
			pagingPolicy['step1_timeout'] = timeouts[0]
		else:
			for x in range(0,len(timeouts)-1):
				key_x = 'step{}'.format(x+1)
				key_x2 = 'step{}_timeout'.format(x+1)
				if x < len(timeouts):
					if steps[x] != steps[x+1]:
						pagingPolicy[key_x] = str(contactMethods[x])
						pagingPolicy[key_x2] = timeouts[x]
					if steps[x] == steps[x+1]:
						pagingPolicy[key_x] = str(contactMethods[x]) + ", " + str(contactMethods[x+1])
						pagingPolicy[key_x2] = timeouts[x]

		# Add the new paging policy dict to user in users_final
		users_final[user]['pagingPolicy'] = pagingPolicy

		# Add step count and unique contact method count to users_final
		step_count = len(set(steps))
		method_count = len(set(contactMethods))
		users_final[user]['number_of_steps'] = step_count
		users_final[user]['unique_contact_methods'] = method_count

		count = count + 1
		print("%s/%s - Fetching policy for %s" % (str(count),str(user_count),str(user)))
		# Add 5 second delay to account for rate limit of 15 times per minute
		sleep(5)
	return users_final

#-------------------------------------------------------------------------------------------------------------
# Audit each user's paging policy for deficiencies

def auditPagingPolicy():
	global users_final
	users_list = users_final.keys()

	for user in users_list:
		crit = 'critical'
		warn = 'warning'
		ok = 'OK'
		reason0 = 'Default policy - email only'
		reason1 = 'No paging policy configured'
		reason2 = 'Only 1 contact method in policy'
		reason3 = '2 contact methods in policy'
		reason4 = '3 or more contact methods in policy'
		reason5 = 'Only one contact method within first 30 minutes'
		methods = users_final[user]['unique_contact_methods']
		steps = users_final[user]['number_of_steps']
		policy = users_final[user]['pagingPolicy' ]

		if methods == 0:
			users_final[user]['policy_audit'] = crit
			users_final[user]['policy_audit_reason'] = reason1

		if methods == 1:
			users_final[user]['policy_audit'] = crit
			users_final[user]['policy_audit_reason'] = reason2

		if methods == 2:
			users_final[user]['policy_audit'] = warn
			users_final[user]['policy_audit_reason'] = reason3

		if methods >= 3:
			users_final[user]['policy_audit'] = ok
			users_final[user]['policy_audit_reason'] = reason4

		if 'step1' in policy:

			step1 = users_final[user]['pagingPolicy']['step1']
			step1_to = users_final[user]['pagingPolicy']['step1_timeout']

			if steps == 1 and step1 == 'email' and step1_to == 5:
				users_final[user]['policy_audit'] = crit
				users_final[user]['policy_audit_reason'] = reason0

			if step1_to >= 30 and ',' not in step1:
				users_final[user]['policy_audit'] = crit
				users_final[user]['policy_audit_reason'] = reason5

			if step1_to >= 30 and ',' not in step1 and methods == 1:
				users_final[user]['policy_audit'] = crit
				users_final[user]['policy_audit_reason'] = str(reason2 + ', ' + reason5)

			if step1_to >= 30 and ',' not in step1 and methods == 2:
				users_final[user]['policy_audit'] = crit
				users_final[user]['policy_audit_reason'] = str(reason3 + ', ' + reason5)

	return users_final


#-------------------------------------------------------------------------------------------------------------
# Write the users_final dictionary to a .csv file

def writeUserAuditToCSV():
	global users_final
	global org_slug

	d = datetime.now()


	f = str("%s/Downloads/%s-VictorOps_User_Audit_%s.csv" % (homedir, org_slug, d.date()))
	file_location = str("%s/Downloads/%s-VictorOps_User_Audit_%s.csv" % (homedir, org_slug, d.date()))

	fields = ['lastName','firstName', 'email','createdDate','verified','passwordLastUpdated','password_age_days','pagingPolicy','number_of_steps','unique_contact_methods','policy_audit','policy_audit_reason']


	with open(f, 'w', encoding = 'utf-8') as f:
		w = csv.DictWriter(f, fields)
		w.writeheader()
		for k,v in users_final.items():
			w.writerow(v)

	print("\n--------------------------------------------------------\n\nInfo for %s users written to file: %s" % (str(user_count), file_location))

#-------------------------------------------------------------------------------------------------------------

def main(argv=None):
	if argv is None:
		argv = sys.argv


	getUsers()

	auditPasswordUpdate()

	getPagingPolicies()

	auditPagingPolicy()

	writeUserAuditToCSV()

if __name__ == '__main__':
	sys.exit(main())