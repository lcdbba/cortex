#!/usr/bin/python

from cortex import app
import cortex.lib.core
import cortex.lib.admin
from cortex.lib.user import does_user_have_permission
from flask import Flask, request, session, redirect, url_for, flash, g, abort, render_template, jsonify
import re
import MySQLdb as mysql
import datetime
import json

################################################################################

@app.route('/admin/tasks')
@cortex.lib.user.login_required
def admin_tasks():
	"""Displays the list of tasks to the user."""

	# Check user permissions
	if not does_user_have_permission("tasks.view"):
		abort(403)

	# Render the page
	return render_template('admin/tasks.html', active='admin', title="Tasks", tasktype='all', json_source=url_for('admin_tasks_json', tasktype='all'))

################################################################################

@app.route('/admin/tasks/json/<tasktype>', methods=['POST'])
@cortex.lib.user.login_required
@app.disable_csrf_check
def admin_tasks_json(tasktype):
	# Check user permissions
	if not does_user_have_permission("tasks.view"):
		abort(403)

	# Get a cursor to the database
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Extract stuff from DataTables requests
	(draw, start, length, order_column, order_asc, search) = _extract_datatables()

	# Choose the order column
	if order_column == 0:
		order_by = "id"
	elif order_column == 1:
		order_by = "module"
	elif order_column == 2:
		order_by = "start"
	elif order_column == 3:
		order_by = "end"
	elif order_column == 4:
		order_by = "elapsed"
	elif order_column == 5:
		order_by = "username"
	elif order_column == 6:
		order_by = "status"
	else:
		app.logger.warn('Invalid ordering column parameter in DataTables request')
		abort(400)

	# Choose order direction
	order_dir = "DESC"
	if order_asc:
		order_dir = "ASC"

	# Determine the task type and add that to the query
	params = ()
	where_clause = ""
	if tasktype == 'all':
		where_clause = '1=1'	# This is just to make 'search' always be able to be an AND and not need an optional WHERE
	elif tasktype == 'user':
		where_clause = '`username` != "scheduler"'
	elif tasktype == 'system':
		where_clause = '`username` = "scheduler"'
	else:
		abort(404)

	# Add on search string if we have one
	if search:
		# escape wildcards
		search = search.replace('%', '\%').replace('_', '\_')
		where_clause = where_clause + " AND (`module` LIKE %s OR `username` LIKE %s) "
		params = params + ('%' + search + '%', '%' + search + '%')

	# Get the total number of tasks
	curd.execute("SELECT COUNT(*) AS `count` FROM `tasks`")
	task_count = curd.fetchone()['count']

	# Get the total number of tasks
	curd.execute("SELECT COUNT(*) AS `count` FROM `tasks` WHERE " + where_clause, params)
	filtered_task_count = curd.fetchone()['count']

	# Get the list of tasks
	curd.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks` WHERE " + where_clause + " ORDER BY `" + order_by + "` " + order_dir + " LIMIT " + str(start) + "," + str(length), params)
	tasks = curd.fetchall()

	# Build an array of tasks
	task_data = []
	for task in tasks:
		# Format elapsed string nicely rather than just seconds which is what comes back from MySQL
		if task['start'] and task['end']:
			task['elapsed'] = str(task['end'] - task['start'])
		else:
			task['elapsed'] = ''

		# Format start time string
		if task['start']:
			task['start'] = task['start'].strftime('%Y-%m-%d %H:%M:%S')

		# Format end time string
		if task['end']:
			task['end'] = task['end'].strftime('%Y-%m-%d %H:%M:%S')

		# Add row to results
		task_data.append([task['id'], task['module'], task['start'], task['end'], task['elapsed'], task['username'], task['status'], task['description']])

	return jsonify(draw=draw, recordsTotal=task_count, recordsFiltered=filtered_task_count, data=task_data)

################################################################################

@app.route('/admin/tasks/active')
@cortex.lib.user.login_required
def admin_tasks_active():
	"""Displays the active tasks"""

	# Check user permissions
	if not does_user_have_permission("tasks.view"):
		abort(403)

	# Get the list of tasks from NeoCortex
	curd = g.db.cursor(mysql.cursors.DictCursor)
	neocortex = cortex.lib.core.neocortex_connect()
	neotasks  = neocortex.active_tasks()
	tasks     = []

	# Get additional information out of the database
	for ntask in neotasks:
		curd.execute("SELECT `id`, `module`, `username`, `start`, `end`, `status`, `description` FROM `tasks` WHERE `id` = %s", (ntask['id'],))
		task = curd.fetchone()
		if not task == None:
			tasks.append(task)

	# Render the page
	return render_template('admin/tasks.html', tasks=tasks, active='admin', title="Active Tasks", tasktype='active')

################################################################################

@app.route('/admin/tasks/user')
@cortex.lib.user.login_required
def admin_tasks_user():
	"""Displays the list of tasks, excluding any system tasks"""

	# Check user permissions
	if not does_user_have_permission("tasks.view"):
		abort(403)

	# Render the page
	return render_template('admin/tasks.html', active='admin', title="User Tasks", tasktype='user', json_source=url_for('admin_tasks_json', tasktype='user'))

################################################################################

@app.route('/admin/tasks/system')
@cortex.lib.user.login_required
def admin_tasks_system():
	"""Displays the list of tasks started by the system"""

	# Check user permissions
	if not does_user_have_permission("tasks.view"):
		abort(403)

	# Render the page
	return render_template('admin/tasks.html', active='admin', title="System Tasks", tasktype='system', json_source=url_for('admin_tasks_json', tasktype='system'))

################################################################################

@app.route('/admin/events/json/<event_source>', methods=['POST'])
@cortex.lib.user.login_required
@app.disable_csrf_check
def admin_events_json(event_source):
	# Check user permissions
	if not does_user_have_permission("events.view"):
		abort(403)

	# Get a cursor to the database
	cur = g.db.cursor()

	# Extract stuff from DataTables requests
	(draw, start, length, order_column, order_asc, search) = _extract_datatables()

	# Choose the order column
	if order_column == 0:
		order_by = "id"
	elif order_column == 1:
		order_by = "start"
	elif order_column == 2:
		order_by = "end"
	elif order_column == 3:
		order_by = "name"
	elif order_column == 4:
		order_by = "desc"
	elif order_column == 5:
		order_by = "source"
	elif order_column == 6:
		order_by = "username"
	elif order_column == 7:
		order_by = "ipaddr"
	elif order_column == 8:
		order_by = "status"
	else:
		app.logger.warn('Invalid ordering column parameter in DataTables request')
		abort(400)

	# Choose order direction
	order_dir = "DESC"
	if order_asc:
		order_dir = "ASC"

	# Determine the event type and add that to the query
	params = ()
	where_clause = ""
	if event_source == 'all':
		where_clause = '1=1'	# This is just to make 'search' always be able to be an AND and not need an optional WHERE
	elif event_source == 'user':
		where_clause = "`username` != 'scheduler'"
	elif event_source == 'scheduler':
		where_clause = "`username` = 'scheduler'"
	elif event_source == 'tasks':
		where_clause = "`source` = 'neocortex.task'"
	else:
		where_clause = "1=1"

	# Add on search string if we have one
	if search:
		# escape wildcards
		search = search.replace('%', '\%').replace('_', '\_')
		where_clause = where_clause + " AND (`name` LIKE %s OR `source` LIKE %s OR `desc` LIKE %s OR `username` LIKE %s OR `ipaddr` LIKE %s) "
		params = params + ('%' + search + '%', '%' + search + '%', '%' + search + '%', '%' + search + '%', '%' + search + '%')

	# Get the total number of events
	cur.execute("SELECT COUNT(*) AS `count` FROM `events`")
	event_count = cur.fetchone()[0]

	# Get the total number of events
	cur.execute("SELECT COUNT(*) AS `count` FROM `events` WHERE " + where_clause, params)
	filtered_event_count = cur.fetchone()[0]

	# Get the list of events
	app.logger.debug("SELECT `id`, `start`, `end`, `name`, `desc`, `source`, `username`, `ipaddr`, `status` FROM `events` WHERE " + where_clause + " ORDER BY `" + order_by + "` " + order_dir + " LIMIT " + str(start) + "," + str(length))

	cur.execute("SELECT `id`, `start`, `end`, `name`, `desc`, `source`, `username`, `ipaddr` FROM `events` WHERE " + where_clause + " ORDER BY `" + order_by + "` " + order_dir + " LIMIT " + str(start) + "," + str(length), params)
	data = cur.fetchall()

	## jsonify uses a particular format for datetime conversion to string,
	## which creates a long string with data we don't care about. we can't 
	## just pre-convert the datetimes, because the result from mysql is a tuple
	## rather than a list. So! We convert everything to a list first, then
	## convert.
	new_data = []
	for record in data:
		record = list(record)
		if type(record[1]) is datetime.datetime:
			record[1] = record[1].strftime('%Y-%m-%d %H:%M:%S %Z')
		if type(record[2]) is datetime.datetime:
			record[2] = record[2].strftime('%Y-%m-%d %H:%M:%S %Z')

		if record[6] is None:
			record[6] = "N/A"
		if record[7] is None:
			record[7] = "N/A"

		new_data.append(record)

	return jsonify(draw=draw, recordsTotal=event_count, recordsFiltered=filtered_event_count, data=new_data)

################################################################################

@app.route('/admin/events')
@app.route('/admin/events/<src>')
@cortex.lib.user.login_required
def admin_events(src="all"):
	"""Displays the list of events, excluding any system events"""

	# Check user permissions
	if not does_user_have_permission("events.view"):
		abort(403)

	# Render the page
	return render_template('admin/events.html', active='admin', title="Events", event_source=src, json_source=url_for('admin_events_json', event_source=src))

################################################################################

@app.route('/admin/specs', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def admin_specs():
	"""Displays a page to edit VM spec settings for the standard VM."""

	# Check user permissions
	if not does_user_have_permission("specs.view"):
		abort(403)

	# Defaults
	vm_spec_json = {}
	vm_specconfig_json = {}
	
	# Get the VM Specs from the DB
	try:
		vm_spec_json = cortex.lib.admin.get_kv_setting('vm.specs', load_as_json=True)
	except ValueError:
		flash("Could not parse JSON from the database.", "alert-danger")
		vm_spec_json = {}
		
	# Get the VM Specs Config from the DB.
	try:
		vm_spec_config_json = cortex.lib.admin.get_kv_setting('vm.specs.config', load_as_json=True)
	except ValueError:
		flash("Could not parse JSON from the database.", "alert-danger")
		vm_spec_config_json = {}

	if request.method == 'POST':

		# Check user permissions
		if not does_user_have_permission("specs.edit"):
			abort(403)

		if 'specs' in request.form:
			try:
				vm_spec_json = json.loads(request.form['specs'])
			except ValueError:
				flash("The JSON you submitted was invalid, your changes have not been saved.", "alert-danger")
				return render_template('admin/specs.html', active='specs', title="VM Specs", vm_spec_json=request.form['specs'], vm_spec_config_json=json.dumps(vm_spec_config_json, sort_keys=True, indent=4))
			else:
				cortex.lib.admin.set_kv_setting('vm.specs', json.dumps(vm_spec_json))

		if 'specsconfig' in request.form:
			try:
				vm_spec_config_json = json.loads(request.form['specsconfig'])
			except ValueError:
				flash("The JSON you submitted was invalid, your changes have not been saved.", "alert-danger")
				return render_template('admin/specs.html', active='specs', title="VM Specs", vm_spec_json=json.dumps(vm_spec_json, sort_keys=True, indent=4), vm_spec_config_json=request.form['specsconfig'])
			else:
				
				# Do some simple validation.
				if 'spec-order' in vm_spec_config_json and not all(s in vm_spec_json for s in vm_spec_config_json['spec-order']):
					flash("You have specified a 'spec-order' which contains specification names not in the 'VM Specification JSON'. Your changes have not been saved.", "alert-warning")
				else:
					cortex.lib.admin.set_kv_setting('vm.specs.config', json.dumps(vm_spec_config_json))
		
	# Render the page
	return render_template('admin/specs.html', active='specs', title="VM Specs", vm_spec_json=json.dumps(vm_spec_json, sort_keys=True, indent=4), vm_spec_config_json=json.dumps(vm_spec_config_json, sort_keys=True, indent=4))

################################################################################

@app.route('/admin/classes', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def admin_classes():
	"""Handles the content of the Admin -> Classes page"""

	# Check user permissions
	if not does_user_have_permission("classes.view"):
		abort(403)

	# On a GET request, display the list of classes page
	if request.method == 'GET':
		classes = cortex.lib.classes.list(hide_disabled=False)
		return render_template('admin/classes.html', classes=classes, active='admin', cmdb_types=app.config['CMDB_CACHED_CLASSES'], title="Classes")

	elif request.method == 'POST':
		# Check user permissions
		if not does_user_have_permission("classes.edit"):
			abort(403)

		action = request.form['action']
		curd   = g.db.cursor()

		if action in ['add_class', 'edit_class']:
			# Validate class name/prefix
			class_name = request.form['class_name']
			if not re.match(r'^[a-z]{1,16}$', class_name):
				flash("The class prefix you sent was invalid. It can only contain lowercase letters and be at least 1 character long and at most 16", "alert-danger")
				return redirect(url_for('admin_classes'))

			# Validate number of digits in hostname/server name
			try:
				class_digits = int(request.form['class_digits'])
			except ValueError:
				flash("The class digits you sent was invalid (it was not a number)." + str(type(class_digits)), "alert-danger")
				return redirect(url_for('admin_classes'))

			if class_digits < 1 or class_digits > 10:
				flash("The class digits you sent was invalid. It must be between 1 and 10.", "alert-danger")
				return redirect(url_for('admin_classes'))

			# Extract whether the new class is active
			if "class_active" in request.form:
				class_disabled = 0
			else:
				class_disabled = 1

			# Validate the comment for the class
			class_comment = request.form['class_comment']
			if not re.match(r'^.{3,512}$', class_comment):
				flash("The class comment you sent was invalid. It must be between 3 and 512 characters long.", "alert-danger")
				return redirect(url_for('admin_classes'))

			# Validate the CMDB type
			class_cmdb_type = request.form['class_cmdb_type']
			if len(class_cmdb_type) == 0:
				class_cmdb_type = None

			# Extract whether the new class links to VMware
			if "class_link_vmware" in request.form:
				class_link_vmware = 1
			else:
				class_link_vmware = 0

			# Check if the class already exists
			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', (class_name,))
			if curd.fetchone() is None:
				class_exists = False
			else:
				class_exists = True

			if action == 'add_class':
				if class_exists:
					flash('A system class already exists with that prefix', 'alert-danger')
					return redirect(url_for('admin_classes'))

				# SQL insert
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES (%s, %s, %s, %s, %s, %s)''', (class_name, class_digits, class_comment, class_disabled, class_link_vmware, class_cmdb_type))
				g.db.commit()

				cortex.lib.core.log(__name__, "systemclass.create", "System class '" + class_name + "' created")
				flash("System class created", "alert-success")
				return redirect(url_for('admin_classes'))
			

			elif action == 'edit_class':
				if not class_exists:
					flash('No system class matching that name/prefix could be found', 'alert-danger')
					return redirect(url_for('admin_classes'))

				curd.execute('''UPDATE `classes` SET `digits` = %s, `disabled` = %s, `comment` = %s, `link_vmware` = %s, `cmdb_type` = %s WHERE `name` = %s''', (class_digits, class_disabled, class_comment, class_link_vmware, class_cmdb_type, class_name))
				g.db.commit()
				cortex.lib.core.log(__name__, "systemclass.edit", "System class '" + class_name + "' edited")

				flash("System class updated", "alert-success")
				return redirect(url_for('admin_classes'))

		elif action == "create_default_classes":

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("srv",))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('srv', 5, 'Standard servers, physical and VMs', 0, 1, 'cmdb_ci_server')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("play",))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('play', 5, 'Sandbox cluster VMs', 0, 1, 'cmdb_ci_server')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("vhost",))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('vhost', 5, 'Virtualisation hosts', 0, 0, 'cmdb_ci_server')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("stg",))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('stg', 5, 'Storage devices', 0, 0, 'cmdb_ci_msd')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("ibs",))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('ibs', 5, 'Infiniband switches', 0, 0, 'cmdb_ci_netgear')''')
				g.db.commit()

			curd.execute('SELECT 1 FROM `classes` WHERE `name` = %s;', ("san",))
			if curd.fetchone() is None:
				curd.execute('''INSERT INTO `classes` (`name`, `digits`, `comment`, `disabled`, `link_vmware`, `cmdb_type`) VALUES ('san', 5, 'Fibre channel switches', 0, 0, 'cmdb_ci_netgear')''')
				g.db.commit()

			cortex.lib.core.log(__name__, "systemclass.createdefaults", "Default system classes added")
			flash("System classes added", "alert-success")
			return redirect(url_for('admin_classes'))

		else:
			abort(400)

################################################################################

@app.route('/admin/maintenance', methods=['GET', 'POST'])
@cortex.lib.user.login_required
def admin_maint():
	"""Allows the user to kick off scheduled jobs on demand"""

	# Check user permissions
	if not does_user_have_permission(["maintenance.vmware", "maintenance.cmdb", "maintenance.expire_vm", "maintenance.sync_puppet_servicenow"]):
		abort(403)

	# Connect to NeoCortex and the database
	neocortex = cortex.lib.core.neocortex_connect()
	curd = g.db.cursor(mysql.cursors.DictCursor)

	# Initial setup
	vmcache_task_id  = None
	sncache_task_id  = None
	vmexpire_task_id = None
	sync_puppet_servicenow_id = None

	if request.method == 'GET':
		# See which tasks are already running
		active_tasks = neocortex.active_tasks()

		for task in active_tasks:
			if task['name'] == '_cache_vmware':
				vmcache_task_id = task['id']
			elif task['name'] == '_cache_servicenow':
				sncache_task_id = task['id']
			elif task['name'] == '_vm_expire':
				sncache_task_id = task['id']
			elif task['name'] == '_sync_puppet_servicenow':
				sync_puppet_servicenow_id = task['id']

		# Render the page
		return render_template('admin/maint.html', active='admin',
			sncache_task_id=sncache_task_id, vmcache_task_id=vmcache_task_id,
			vmexpire_task_id=vmexpire_task_id, sync_puppet_servicenow_id=sync_puppet_servicenow_id,
			title="Maintenance Tasks"
		)

	else:
		# Find out what task to start
		module = request.form['task_name']

		# Start the appropriate internal task
		if module == 'vmcache':
			# Check user permissions
			if not does_user_have_permission("maintenance.vmware"):
				abort(403)

			task_id = neocortex.start_internal_task(session['username'], 'cache_vmware.py', '_cache_vmware', description="Caches information about virtual machines, datacenters and clusters from VMware")
		elif module == 'sncache':
			# Check user permissions
			if not does_user_have_permission("maintenance.cmdb"):
				abort(403)

			task_id = neocortex.start_internal_task(session['username'], 'cache_servicenow.py', '_cache_servicenow', description="Caches server CIs from the ServiceNow CMDB")
		elif module == 'vmexpire':
			# Check user permissions
			if not does_user_have_permission("maintenance.expire_vm"):
				abort(403)

			task_id = neocortex.start_internal_task(session['username'], 'vm_expire.py', '_vm_expire', description="Turns off VMs which have expired")
		elif module == 'sync_puppet_servicenow':
			# Check user permissions
			if not does_user_have_permission("maintenance.sync_puppet_servicenow"):
				abort(403)
			task_id = neocortex.start_internal_task(session['username'], 'sync_puppet_servicenow.py', '_sync_puppet_servicenow', description="Sync Puppet facts with ServiceNow")
		else:
			app.logger.warn('Unknown module name specified when starting task')
			abort(400)

		# Show the user the status of the task
		return redirect(url_for('task_status', id=task_id))

################################################################################

def _extract_datatables():
	# Validate and extract 'draw' parameter. This parameter is simply a counter
	# that DataTables uses internally.
	if 'draw' in request.form:
		draw = int(request.form['draw'])
	else:
		app.logger.warn('`draw` parameter missing from DataTables request')
		abort(400)

	# Validate and extract 'start' parameter. This parameter is the index of the
	# first row to return.
	if 'start' in request.form:
		start = int(request.form['start'])
	else:
		app.logger.warn('`start` parameter missing from DataTables request')
		abort(400)

	# Validate and extract 'length' parameter. This parameter is the number of
	# rows that we should return
	if 'length' in request.form:
		length = int(request.form['length'])
		if length < 0:
			# MySQL Max Length
			length = "18446744073709551610"
	else:
		app.logger.warn('`length` parameter missing from DataTables request')
		abort(400)

	# Validate and extract ordering column. This parameter is the index of the
	# column on the HTML table to order by
	if 'order[0][column]' in request.form:
		order_column = int(request.form['order[0][column]'])
	else:
		order_column = 0

	# Validate and extract ordering direction. 'asc' for ascending, 'desc' for
	# descending.
	if 'order[0][dir]' in request.form:
		if request.form['order[0][dir]'] == 'asc':
			order_asc = True
		elif request.form['order[0][dir]'] == 'desc':
			order_asc = False
		else:
			app.logger.warn('Invalid `order[0][dir]` parameter in DataTables request')
			abort(400)
	else:
		order_asc = False

	# Handle the search parameter. This is the textbox on the DataTables
	# view that the user can search by typing in
	search = None
	if 'search[value]' in request.form:
		if request.form['search[value]'] != '':
			if type(request.form['search[value]']) is not str and type(request.form['search[value]']) is not unicode:
				search = str(request.form['search[value]'])
			else:
				search = request.form['search[value]']

	return (draw, start, length, order_column, order_asc, search)
