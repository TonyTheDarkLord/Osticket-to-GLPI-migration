import mysql.connector
import requests
import json
import os
import base64
import mimetypes
from datetime import datetime

# OsTicket database connection
osticket_db = mysql.connector.connect(
    host="localhost",
    user="",
    password="",
    database="osticket"
)

# GLPI API configuration
glpi_url = "https://tickets.url/apirest.php"
glpi_app_token = ""
glpi_user_token = ""

# Mapping of OsTicket department IDs to GLPI entity IDs
department_to_entity_map = {
    # Example: 1: 5 means OsTicket department ID 1 maps to GLPI entity ID 5
    1: 1,
}

# Mapping of OsTicket status IDs to GLPI status IDs
status_map = {
    # Example: 1: 2 means OsTicket status ID 1 maps to GLPI status ID 2
    1: 1,
}

# Mapping of OsTicket staff IDs to GLPI technician IDs
staff_to_technician_map = {
    # Example: 1: 3 means OsTicket staff ID 1 maps to GLPI technician ID 3
    1: 3,
}

def get_osticket_tickets():
    cursor = osticket_db.cursor(dictionary=True)
    query = """
    SELECT t.ticket_id, t.number, t.user_id, t.user_email_id, t.status_id, t.dept_id,
       t.topic_id, t.staff_id, t.isanswered, t.duedate, t.closed, t.lastupdate, t.created,
       tc.subject, tc.priority, t.sla_id,
       (SELECT te.body
        FROM ost_thread_entry te
        INNER JOIN ost_thread ON (ost_thread.id = te.thread_id)
        INNER JOIN ost_ticket ON (ost_ticket.ticket_id = ost_thread.object_id)
        WHERE ost_ticket.ticket_id = t.ticket_id
        ORDER BY te.created LIMIT 1) AS ticket_body,
       u.name AS requester_name, ue.address AS requester_email
    FROM ost_ticket t
    LEFT JOIN ost_ticket__cdata tc ON t.ticket_id = tc.ticket_id
    LEFT JOIN ost_user u ON t.user_id = u.id
    LEFT JOIN ost_user_email ue ON t.user_id = ue.user_id
    JOIN ost_thread th ON t.ticket_id = th.object_id
    WHERE th.object_type = 'T'
    """
    # This can be added to the Where syntax to segment migration
    # AND t.ticket_id > 499 AND t.ticket_id < 10001
    cursor.execute(query)
    return cursor.fetchall()

def get_osticket_tickets_first_entry(ticket_id):
    cursor = osticket_db.cursor(dictionary=True)
    query = """
    SELECT te.body
        FROM ost_thread_entry te
        INNER JOIN ost_thread ON (ost_thread.id = te.thread_id)
        INNER JOIN ost_ticket ON (ost_ticket.ticket_id = ost_thread.object_id)
        WHERE ost_ticket.ticket_id = %s
        ORDER BY te.created LIMIT 1
    """
    cursor.execute(query)
    return cursor.fetchall()

def get_ticket_threads(ticket_id):
    cursor = osticket_db.cursor(dictionary=True)
    query = """
    SELECT te.id, te.thread_id, te.staff_id, te.user_id, te.type, te.poster,
           te.body, te.created, te.updated, te.source, te.flags,
           t.object_id, t.object_type,
           s.firstname AS staff_firstname, s.lastname AS staff_lastname,
           u.name AS user_name, ue.address AS user_email
    FROM ost_thread_entry te
    JOIN ost_thread t ON te.thread_id = t.id
    LEFT JOIN ost_staff s ON te.staff_id = s.staff_id
    LEFT JOIN ost_user u ON te.user_id = u.id
    LEFT JOIN ost_user_email ue ON u.id = ue.user_id
    WHERE t.object_id = %s AND t.object_type = 'T'
    ORDER BY te.created ASC
    """
    cursor.execute(query, (ticket_id,))
    return cursor.fetchall()

def get_ticket_collaborators(ticket_id):
    cursor = osticket_db.cursor(dictionary=True)
    query = """
    SELECT ue.address as email, tc.role, u.name
    FROM ost_thread_collaborator tc
    JOIN ost_thread t ON tc.thread_id = t.id
    JOIN ost_user u ON tc.user_id = u.id
    JOIN ost_user_email ue ON u.id = ue.user_id
    WHERE t.object_id = %s AND t.object_type = 'T'
    """
    cursor.execute(query, (ticket_id,))
    return cursor.fetchall()

def get_osticket_attachments(thread_entry_id):
    #print(thread_entry_id)
    cursor = osticket_db.cursor(dictionary=True)
    query = """
    SELECT a.id, a.object_id, a.type, a.file_id, a.name as attachment_name, a.inline, a.lang,
           f.ft, f.bk, f.type as file_type, f.size, f.key, f.signature, f.name as file_name, f.attrs, f.created, te.created as created_date
    FROM ost_thread_entry te
    JOIN ost_attachment a ON a.object_id = te.id
    JOIN ost_file f ON a.file_id = f.id
    WHERE te.id = %s AND a.type = 'H'
    ORDER BY te.created ASC
    """
    cursor.execute(query, (thread_entry_id,))
    return cursor.fetchall()

def get_file_content(file_id):
    cursor = osticket_db.cursor(dictionary=True)

    # First, check if the file is stored in the filesystem
    query = "SELECT bk, `key` FROM ost_file WHERE id = %s"
    cursor.execute(query, (file_id,))
    result = cursor.fetchone()

    if result and result['bk'] == 'F':  # 'F' typically indicates filesystem storage
        # File is stored in the filesystem
        file_key = result['key']
        # Construct the file path based on osTicket's file storage structure
        file_path = os.path.join('/opt/osticket/data/attachments/', file_key[:1], file_key)
        try:
            with open(file_path, 'rb') as file:
                return file.read()
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return None
    else:
        # File is stored in the database
        query = """
        SELECT filedata
        FROM ost_file_chunk
        WHERE file_id = %s
        ORDER BY chunk_id
        """
        cursor.execute(query, (file_id,))
        chunks = cursor.fetchall()
        return b''.join(chunk['filedata'] for chunk in chunks)

def init_glpi_session():
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"user_token {glpi_user_token}",
        "App-Token": glpi_app_token
    }
    response = requests.get(f"{glpi_url}/initSession", headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {response.headers}")
    print(f"Response Content: {response.text}")

    if response.status_code == 200:
        try:
            return response.json()['session_token']
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {e}")
            print(f"Response content: {response.text}")
            raise
    else:
        print(f"Error initializing session. Status code: {response.status_code}")
        print(f"Response content: {response.text}")
        raise Exception("Failed to initialize GLPI session")

def kill_glpi_session(session_token):
    headers = {
        "Content-Type": "application/json",
        "Session-Token": session_token,
        "App-Token": glpi_app_token
    }
    requests.get(f"{glpi_url}/killSession", headers=headers)

def get_or_create_glpi_user(session_token, email, name=None):
    headers = {
        "Content-Type": "application/json",
        "Session-Token": session_token,
        "App-Token": glpi_app_token
    }

    #print(email)
    if email == None:
        return 0

    # Search for existing user
    search_params = {
        'criteria[0][field]': 5, # this is email field
        'criteria[0][searchtype]': 'match',
        'criteria[0][value]': email,
        'forcedisplay[0]': 2  # ID field
    }
    response = requests.get(f"{glpi_url}/search/User", headers=headers, params=search_params)
    search_result = response.json()

    if search_result['totalcount'] > 0:
        return search_result['data'][0]["2"]  # Return the ID of the first matching user

    search_params = {
        'criteria[0][field]': 1, # if mail not found I try to find it in user field the same email
        'criteria[0][searchtype]': 'match',
        'criteria[0][value]': email,
        'forcedisplay[0]': 2  # ID field
    }
    response = requests.get(f"{glpi_url}/search/User", headers=headers, params=search_params)
    search_result = response.json()

    if search_result['totalcount'] > 0:
        return search_result['data'][0]["2"]  # Return the ID of the first matching user

    # If user doesn't exist, create a new one
    payload = {
        "input": {
            "name": email,  # Use provided name or part before @ as username
            "realname": name or "",
            "firstname": "",
            "usercategories_id": 0,
            "usertitles_id": 0,
            "email": email,
            "auths_id": 1,
            "profiles_id": 1,  # Assign a default profile ID
            "entities_id": 0  # Assign to root entity
        }
    }
    response = requests.post(f"{glpi_url}/User", headers=headers, json=payload)
    new_user = response.json()
    if 'id' in new_user:
        return new_user['id']
    else:
        raise Exception(f"Failed to create user: {new_user}")

def impersonate_user(session_token, user_id):
    headers = {
        "Content-Type": "application/json",
        "Session-Token": session_token,
        "App-Token": glpi_app_token
    }
    data = {"users_id": user_id}
    response = requests.post(f"{glpi_url}/changeActiveEntities/", headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"Failed to impersonate user: {response.text}")

def create_glpi_ticket(session_token, ticket_data, attachments=None):
    headers = {
        "Content-Type": "application/json",
        "Session-Token": session_token,
        "App-Token": glpi_app_token
    }

    # I want to identificate specific user with specific id cause user find not work very well, else find correct one
    if ticket_data['requester_email'] == "no_reply@example.com":
        requester_id = 999999
    else:
        requester_id = get_or_create_glpi_user(session_token, ticket_data['requester_email'], ticket_data['requester_name'])

    # Impersonate the requester
    impersonate_user(session_token, requester_id)

    # Map OsTicket department ID to GLPI entity ID
    entity_id = department_to_entity_map.get(ticket_data['dept_id'], 0)  # Default to root entity (0) if not found

    # Map OsTicket status ID to GLPI status ID
    status_id = status_map.get(ticket_data['status_id'], 1)  # Default to 'New' (1) if not found

    # Get Staff ID for the ticket
    if ticket_data['staff_id'] != 0:
        staff_id = staff_to_technician_map.get(ticket_data['staff_id'], 0)
    else:
        staff_id = 0

    payload = {
        "input": {
            "name": ticket_data['subject'],
            "content": ticket_data.get('ticket_body', 'No ticket content'),
            "_users_id_requester": requester_id,
            "_users_id_creator": requester_id,
            "entities_id": entity_id,
            "status": status_id,
            "date": str(ticket_data['created']),
            "date_creation": str(ticket_data['created']),
            "date_mod": str(ticket_data['lastupdate']),
            "priority": ticket_data['priority'],
            "itilcategories_id": ticket_data['topic_id'],
            "type": 1,
            "urgency": 3,
            "impact": 3,
            "_auto_import": True,
        }
    }

    if staff_id != 0:
        payload['input']["_users_id_assign"] = staff_id

    if ticket_data['closed']:
        payload['input']["closedate"] = str(ticket_data['closed'])

    response = requests.post(f"{glpi_url}/Ticket", headers=headers, json=payload)
    #print(response.text)
    #print(response)
    return response.json()

def add_watcher_to_glpi_ticket(session_token, ticket_id, watcher_email, watcher_name):
    headers = {
        "Content-Type": "application/json",
        "Session-Token": session_token,
        "App-Token": glpi_app_token
    }

    watcher_id = get_or_create_glpi_user(session_token, watcher_email, watcher_name)

    payload = {
        "input": {
            "tickets_id": ticket_id,
            "users_id": watcher_id,
            "type": 3  # 3 is the type for watchers in GLPI
        }
    }

    response = requests.post(f"{glpi_url}/Ticket_User", headers=headers, json=payload)
    return response.json()

def add_followup_to_glpi_ticket(session_token, ticket_id, followup_data, attachments=None):
    headers = {
        "Content-Type": "application/json",
        "Session-Token": session_token,
        "App-Token": glpi_app_token
    }

    if followup_data['staff_id'] != 0:
        user_id = staff_to_technician_map.get(followup_data['staff_id'], 0)
    elif followup_data['user_id'] != 0:
        user_id = get_or_create_glpi_user(session_token, followup_data['user_email'], followup_data['user_name'])
    else:
        user_id = 0  # Default to 0 if no user or staff is associated

    payload = {
        "input": {
            "items_id": ticket_id,
            "itemtype": "Ticket",
            "content": followup_data['body'],
            "date_creation": str(followup_data['created']),
            "users_id": user_id,
            "is_private": 0 if followup_data['type'] == 'M' else 1,  # Assuming 'M' is for public messages not works very well
        }
    }
    
    response = requests.post(f"{glpi_url}/ITILFollowup", headers=headers, json=payload)
    return response.json()

def add_document_to_glpi_ticket(session_token, ticket_id, document_data, file_content, followup_data, entity_id=0):
    headers = {
        "Session-Token": session_token,
        "App-Token": glpi_app_token
    }

    #if file_content is None:
    #    print(f"Skipping attachment {document_data['attachment_name']} due to missing file content")
    #    return None

    if followup_data['staff_id'] != 0:
        user_id = staff_to_technician_map.get(followup_data['staff_id'], 0)
    elif followup_data['user_id'] != 0:
        user_id = get_or_create_glpi_user(session_token, followup_data['user_email'], followup_data['user_name'])
    else:
        user_id = 0  # Default to 0 if no user or staff is associated

    file_name = document_data['attachment_name'] or document_data['file_name']
    file_mime = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'

    files = {
        'uploadManifest': (None, json.dumps({
            'input': {
                'name': file_name,
                "entities_id": entity_id,
                "users_id": user_id,
                'date_creation': str(document_data['created_date']),
                '_filename': [file_name]
            }
        }), 'application/json'),
        'filename[0]': (file_name, file_content, file_mime)
    }

    response = requests.post(f"{glpi_url}/Document", headers=headers, files=files)

    if response.status_code == 201:
        document_id = response.json()['id']

        # Link the document to the ticket
        link_payload = {
            'input': {
                'itemtype': 'Ticket',
                'items_id': ticket_id,
                "users_id": user_id,
                'date_creation': str(document_data['created_date']),
                'documents_id': document_id
            }
        }
        link_response = requests.post(f"{glpi_url}/Document_Item", headers=headers, json=link_payload)

        if link_response.status_code == 201:
            #print(f"Document {document_id} linked to ticket {ticket_id}")
            return document_id
        else:
            print(f"Failed to link document {document_id} to ticket {ticket_id}")
            print(f"Status code: {link_response.status_code}")
            #print(f"Response content: {link_response.text}")

            # If linking fails, we should delete the uploaded document to avoid orphaned documents
            delete_response = requests.delete(f"{glpi_url}/Document/{document_id}", headers=headers)
            # if delete_response.status_code == 200:
                # print(f"Deleted orphaned document {document_id}")
            # else:
                # print(f"Failed to delete orphaned document {document_id}")

            return None
    else:
        print(f"Failed to upload document for ticket {ticket_id}")
        print(f"Status code: {response.status_code}")
        #print(f"Response content: {response.text}")
        return None

def associate_attachments_with_followup(session_token, followup_id, attachments):
    headers = {
        "Session-Token": session_token,
        "App-Token": glpi_app_token
    }

    for attachment in attachments:
        file_content = get_file_content(attachment['file_id'])
        file_name = attachment['attachment_name'] or attachment['file_name']
        file_mime = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'

        files = {
            'uploadManifest': (None, json.dumps({
                'input': {
                    'name': file_name,
                    '_filename': [file_name]
                }
            }), 'application/json'),
            'filename[0]': (file_name, file_content, file_mime)
        }

        response = requests.post(f"{glpi_url}/Document", headers=headers, files=files)

        if response.status_code == 201:
            document_id = response.json()['id']

            # Link the document to the followup
            link_payload = {
                'input': {
                    'itemtype': 'ITILFollowup',
                    'items_id': followup_id,
                    'documents_id': document_id
                }
            }
            link_response = requests.post(f"{glpi_url}/Document_Item", headers=headers, json=link_payload)

            if link_response.status_code == 201:
                print(f"Document {document_id} linked to followup {followup_id}")
            else:
                print(f"Failed to link document {document_id} to followup {followup_id}")
        else:
            print(f"Failed to upload document for followup {followup_id}")

def main():
    session_token = init_glpi_session()
    try:
        osticket_data = get_osticket_tickets()

        for ticket in osticket_data:
            # Create the main ticket in GLPI
            glpi_ticket = create_glpi_ticket(session_token, ticket, [])


            if 'id' not in glpi_ticket:
                print(f"Failed to create ticket: {glpi_ticket}")
                continue

            # Get and add collaborators as watchers
            collaborators = get_ticket_collaborators(ticket['ticket_id'])
            for collaborator in collaborators:
                add_watcher_to_glpi_ticket(session_token, glpi_ticket['id'], collaborator['email'], collaborator['name'])

            # Add followups
            threads = get_ticket_threads(ticket['ticket_id'])
            entity_id = department_to_entity_map.get(ticket['dept_id'], 0)
            first = True
            for thread in threads:
                if not first:
                    thread_attachments = get_osticket_attachments(thread['id'])
                    followup = add_followup_to_glpi_ticket(session_token, glpi_ticket['id'], thread, thread_attachments)
                    if followup and 'id' in followup:
                        #print(f"Successfully added followup with ID {followup['id']} to ticket {glpi_ticket['id']}")
                        for attachment in thread_attachments:
                            file_content = get_file_content(attachment['file_id'])
                            document_id = add_document_to_glpi_ticket(session_token, glpi_ticket['id'], attachment, file_content, thread, entity_id)
                            if document_id is None:
                                print(f"Failed to add attachment {attachment['attachment_name']} to ticket {glpi_ticket['id']}")
                            # else:
                                # print(f"Successfully added attachment {attachment['attachment_name']} (Document ID: {document_id}) to ticket {glpi_ticket['id']}")
                    else:
                        print(f"Failed to add followup to ticket {glpi_ticket['id']}")
                else:
                    thread_attachments = get_osticket_attachments(thread['id'])
                    for attachment in thread_attachments:
                        file_content = get_file_content(attachment['file_id'])
                        document_id = add_document_to_glpi_ticket(session_token, glpi_ticket['id'], attachment, file_content, thread, entity_id)
                        if document_id is None:
                            print(f"Failed to add attachment {attachment['attachment_name']} to ticket {glpi_ticket['id']}")
                        # else:
                            # print(f"Successfully added attachment {attachment['attachment_name']} (Document ID: {document_id}) to ticket {glpi_ticket['id']}")
                first = False

        print("Migration completed successfully!")
    finally:
        kill_glpi_session(session_token)

if __name__ == "__main__":
    main()
