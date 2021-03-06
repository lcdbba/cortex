import requests
import ldap
from urlparse import urljoin

def run(helper, options):

	# Iterate over the actions that we have to perform
	for action in options['actions']:
		# Start the event
		helper.event(action['id'], action['desc'])

		if action['id'] == "vm.poweroff":
			r = action_vm_poweroff(action, helper)
		elif action['id'] == "vm.delete":
			r = action_vm_delete(action, helper)
		elif action['id'] == "cmdb.update":
			r = action_cmdb_update(action, helper)
		elif action['id'] == "cmdb.relationships.delete":
			r = action_cmdb_relationships_delete(action, helper)
		elif action['id'] == "dns.delete":
			r = action_dns_delete(action, helper)
		elif action['id'] == "puppet.cortex.delete":
			r = action_puppet_cortex_delete(action, helper)
		elif action['id'] == "puppet.master.delete":
			r = action_puppet_master_delete(action, helper)
		elif action['id'] == "ad.delete":
			r = action_ad_delete(action, helper)
		elif action['id'] == "ticket.ops":
			r = action_ticket_ops(action, helper, options['wfconfig'])
		elif action['id'] == "tsm.decom":
			r = action_tsm_decom(action, helper)
		elif action['id'] == "rhn5.delete":
			r = action_rhn5_delete(action, helper)
		elif action['id'] == "satellite6.delete":
			r = action_satellite6_delete(action, helper) 
		elif action['id'] == "sudoldap.update":
			r = action_sudoldap_update(action, helper, options['wfconfig'])
		elif action['id'] == "sudoldap.delete":
			r = action_sudoldap_delete(action, helper, options['wfconfig'])
		elif action['id'] == "graphite.delete":
			r = action_graphite_delete(action, helper, options['wfconfig'])
		elif action['id'] == "system.update_decom_date":
			r = action_update_decom_date(action, helper) 
			
		# End the event (don't change the description) if the action
		# succeeded. The action_* functions either raise Exceptions or
		# end the events with a failure message on errors.
		if r:
			helper.end_event()

################################################################################

def action_vm_poweroff(action, helper):
	# Get the managed VMware VM object
	vm = helper.lib.vmware_get_vm_by_uuid(action['data']['uuid'], action['data']['vcenter'])

	# Not finding the VM is fatal:
	if not vm:
		raise helper.lib.TaskFatalError(message="Failed to power off VM. Could not locate VM in vCenter")

	# Power off the VM
	task = helper.lib.vmware_vm_poweroff(vm)

	# Wait for the task to complete
	helper.lib.vmware_task_wait(task)

	return True

################################################################################

def action_vm_delete(action, helper):
	# Get the managed VMware VM object
	vm = helper.lib.vmware_get_vm_by_uuid(action['data']['uuid'], action['data']['vcenter'])

	# Not finding the VM is fatal:
	if not vm:
		raise helper.lib.TaskFatalError(message="Failed to delete VM. Could not locate VM in vCenter")

	# Delete the VM
	task = helper.lib.vmware_vm_delete(vm)

	# Wait for the task to complete
	if not helper.lib.vmware_task_wait(task):
		raise helper.lib.TaskFatalError(message="Failed to delete the VM. Check vCenter for more information")
	helper.lib.delete_system_from_cache(action['data']['uuid'])
	return True

################################################################################

def action_cmdb_update(action, helper):
	try:
		# This will raise an Exception if it fails, but it is not fatal
		# to the decommissioning process
		helper.lib.servicenow_mark_ci_deleted(action['data'])
		return True
	except Exception as e:
		helper.end_event(success=False, description=str(e))
		return False

################################################################################

def action_cmdb_relationships_delete(action, helper):
	try:
		# Remove the CI relationships
		(successes, warnings) = helper.lib.servicenow_remove_ci_relationships(action['data'])

		# Special action-end-cases
		if successes == 0 and warnings == 0:
			# This technically shouldn't happen unless somebody deletes them between the "Check System"
			# stage and the task actually running
			helper.end_event(success=True, warning=True, description="Found no CI relationships to remove")
		elif successes == 0 and warnings > 0:
			helper.end_event(success=False, description="Failed to remove any CI relationships")
		elif successes > 0 and warnings > 0:
			helper.end_event(success=True, warning=True, description="Failed to remove some CI relationships: " + str(successes) + " succeeded, " + str(warnings) + " failed")

		return True
	except Exception as e:
		helper.end_event(success=False, description=str(e))
		return False

################################################################################

def action_dns_delete(action, helper):
	try:
		helper.lib.infoblox_delete_host_record_by_ref(action['data'])
		return True
	except Exception as e:
		helper.end_event(success=False, description=str(e))
		return False

################################################################################

def action_puppet_cortex_delete(action, helper):
	try:
		helper.lib.puppet_enc_remove(action['data'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to remove Puppet node from ENC: " + str(e))
		return False

################################################################################

def action_puppet_master_delete(action, helper):
	# Build the URL
	base_url = helper.config['PUPPET_AUTOSIGN_URL']
	if not base_url.endswith('/'):
		base_url += '/'
	clean_url = base_url + 'cleannode/' + str(action['data'])
	deactivate_url = base_url + 'deactivatenode/' + str(action['data'])

	# Send the request to Cortex Puppet Bridge to clean the node
	try:
		r = requests.get(clean_url, headers={'X-Auth-Token': helper.config['PUPPET_AUTOSIGN_KEY']}, verify=helper.config['PUPPET_AUTOSIGN_VERIFY'])
	except Exception as ex:
		helper.end_event(success=False, description="Failed to remove node from Puppet Master: " + str(ex))
		return False

	# Check return code
	if r.status_code != 200:
		helper.end_event(success=False, description="Failed to remove node from Puppet Master. Cortex Puppet Bridge returned error code " + str(r.status_code))
		return False

	# Send the request to Cortex Puppet Bridge to deactivate the node
	try:
		r = requests.get(deactivate_url, headers={'X-Auth-Token': helper.config['PUPPET_AUTOSIGN_KEY']}, verify=helper.config['PUPPET_AUTOSIGN_VERIFY'])
	except Exception as ex:
		helper.end_event(success=False, description="Failed to deactivate node on Puppet Master: " + str(ex))
		return False

	# Check return code
	if r.status_code != 200:
		helper.end_event(success=False, description="Failed to deactivate node on Puppet Master. Cortex Puppet Bridge returned error code " + str(r.status_code))
		return False

	return True

################################################################################

def action_ad_delete(action, helper):
	try:
		helper.lib.windows_delete_computer_object(action['data']['env'], action['data']['hostname'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to remove AD object: " + str(e))
		return False

################################################################################

def action_ticket_ops(action, helper, wfconfig):
	try:
		short_desc = "Finish manual decommissioning steps of " + action['data']['hostname']
		message  = 'Cortex has decommissioned the system ' + action['data']['hostname'] + '.\n\n'
		message += 'Please perform the final, manual steps of the decommissioning process:\n'
		message += ' - Remove the system from monitoring\n'
		message += ' - Remove any associated perimeter firewall rules\n'
		message += ' - Remove any associated load balancer configuration\n'
		message += ' - Update any relevant documentation\n'

		helper.lib.servicenow_create_ticket(short_desc, message, wfconfig['TICKET_OPENER_SYS_ID'], wfconfig['TICKET_TEAM'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to raise ticket: " + str(e))
		return False

################################################################################

def action_tsm_decom(action, helper):
	try:
		helper.lib.tsm_decom_system(action['data']['NAME'], action['data']['SERVER'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to decomission system in TSM")
		return False

################################################################################

def action_rhn5_delete(action, helper):
	try:
		(rhn,key) = helper.lib.rhn5_connect()
		rhn.system.deleteSystem(key, int(action['data']['id']))
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to delete the system object in RHN5")
		return False

def action_satellite6_delete(action, helper):
	try:
		try:
			helper.lib.satellite6_disassociate_host(action['data']['id'])
		except Exception as e:
			helper.end_event(success=False, description="Failed to disassociate the host object with ID {0} from a VM in Satellite 6".format(action['data']['id']))
			return False

		try:
			helper.lib.satellite6_delete_host(action['data']['id'])
		except Exception as e:
			helper.end_event(success=False, description="Failed to delete the host object with ID {0} in Satellite 6".format(action['data']['id']))
			return False

		# We disassociated and deleted successfully.
		return True

	except Exception as e:
		helper.end_event(success=False, description="Failed to delete the host object in Satellite 6")
		return False

################################################################################

def action_sudoldap_update(action, helper, wfconfig):
	try:
		# Connect to LDAP
		l = ldap.initialize(wfconfig['SUDO_LDAP_URL'])
		l.bind_s(wfconfig['SUDO_LDAP_USER'], wfconfig['SUDO_LDAP_PASS'])

		# Replace the value of sudoHost with the calculated list
		l.modify_s(action['data']['dn'], [(ldap.MOD_DELETE, 'sudoHost', str(action['data']['value']))])
		
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to update the object in sudoldap: " + str(e))
		return False

################################################################################

def action_sudoldap_delete(action, helper, wfconfig):
	try:
		# Connect to LDAP
		l = ldap.initialize(wfconfig['SUDO_LDAP_URL'])
		l.bind_s(wfconfig['SUDO_LDAP_USER'], wfconfig['SUDO_LDAP_PASS'])
		
		# Delete the entry
		l.delete_s(action['data']['dn'])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to delete the object in sudoldap")
		return False

################################################################################

def action_update_decom_date(action, helper):
	try:
		helper.lib.update_decom_date(action["data"]["system_id"])
		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to update the decommission date in Cortex")
		return False

################################################################################

def action_graphite_delete(action, helper, wfconfig):
	try:
		# Make the REST call to delete the metrics
		url = urljoin(helper.config['GRAPHITE_URL'], '/host/' + action['data']['host'])
		r = requests.delete(url, auth=(helper.config['GRAPHITE_USER'], helper.config['GRAPHITE_PASS']))

		if r.status_code != 200:
			helper.end_event(success=False, description="Failed to remove metrics from Graphite. CarbonHTTPInterface returned error code " + str(r.status_code))
			return False

		return True
	except Exception as e:
		helper.end_event(success=False, description="Failed to remove the metrics from Graphite: " + str(e))
		return False

