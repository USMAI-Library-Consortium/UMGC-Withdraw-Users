import os
from datetime import datetime, date, timedelta
import xmltodict
import requests
import time
from json import JSONDecodeError
import xml.etree.ElementTree as ElementTree
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY")
TEST_BARCODE = os.getenv("TEST_BARCODE")
RUN_JOBS = os.getenv("RUN_JOBS", "false").lower() == "true"


def check_valid_status() -> bool:
    """Returns whether it's okay to go ahead with the process.
    Checks both Alma API connection and that the status date is in the current month."""
    user_data = requests.get(f"https://api-na.hosted.exlibrisgroup.com/almaws/v1/users/{TEST_BARCODE}",
                             headers={"Authorization": f"apikey {API_KEY}",
                                      "Accept": "application/json"})

    try:
        status_date_string = user_data.json()["status_date"]
        print(f"Status Date on Test User is {status_date_string}")
    except KeyError:
        print(f"User with barcode {TEST_BARCODE} not found.")
        return False
    except JSONDecodeError:
        try:
            root = ElementTree.fromstring(user_data.content)
            error_message = root.find("{http://com/exlibris/urm/general/xmlbeans}errorList").find("{http://com/exlibris/urm/general/xmlbeans}error").find("{http://com/exlibris/urm/general/xmlbeans}errorMessage").text
            print(f"Error: {error_message}")
        except Exception as e:
            print(e)
            print(user_data.content)
        return False

    # Check whether the status was changed in the current month
    # If not, the job is not ready to run
    status_date = date.fromisoformat(status_date_string.replace("Z", ""))
    first_day_of_month = date.today().replace(day=1)

    return True if status_date >= first_day_of_month else False


def create_employee_set() -> str | None:
    print("Creating terminated employee set...")
    # 1 - Pull terminated employees from alma analytics
    result = requests.get(
        f"https://api-na.hosted.exlibrisgroup.com/almaws/v1/analytics/reports?path=/shared/University of Maryland Global Campus (UMGC) 01USMAI_UMGC/Reports/Terminated Employees&limit=1000",
        headers={"Authorization": f"apikey {API_KEY}"})

    # Parse out the primary identifiers of the users
    result_json = xmltodict.parse(result.content)
    user_data = result_json["report"]["QueryResult"]["ResultXml"]["rowset"]["Row"]
    terminated_employee_barcodes = [user["Column4"] for user in user_data]

    # 2 - Create a set with the employees
    set_name = f"Terminated Employees as of {datetime.now().strftime('%m/%d/%Y %H:%M:%S')}"
    set_body = {
        "link": "",
        "name": set_name,
        "description": "Set of physical items.",
        "content": {
            "value": "USER",
        },
        "type": {
            "value": "ITEMIZED",
        },
        "private": {
            "value": "true",
        }
    }
    set_result = requests.post(f"https://api-na.hosted.exlibrisgroup.com/almaws/v1/conf/sets/",
                               headers={"Authorization": f"apikey {API_KEY}",
                                        "Accept": "application/json"},
                               json=set_body)
    set_url = set_result.json()["link"]
    set_id = set_result.json()["id"]

    # 3 - Add Members to Set
    set_body = {
        "content": {
            "value": "USER",
        },
        "type": {
            "value": "ITEMIZED",
        },
        "members": {
            "total_record_count": len(terminated_employee_barcodes),
            "member": [
                {
                    "link": "",
                    "id": user_id
                } for user_id in terminated_employee_barcodes
            ]
        }
    }
    add_members_result = requests.post(f"{set_url}?op=add_members", json=set_body,
                                       headers={"Authorization": f"apikey {API_KEY}",
                                                "Accept": "application/json",
                                                "Content-Type": "application/json"}
                                       )
    if add_members_result.status_code == 200:
        return set_id
    else:
        print("Error creating employee set.")
        return None


def create_student_set() -> str | None:
    print("Creating inactive student set...")
    # 1 - Pull inactive students
    result = requests.get(
        f"https://api-na.hosted.exlibrisgroup.com/almaws/v1/analytics/reports?path=/shared/University of Maryland Global Campus (UMGC) 01USMAI_UMGC/Reports/Inactive Students&limit=1000",
        headers={"Authorization": f"apikey {API_KEY}"})

    # Parse out the primary identifiers of the students
    result_json = xmltodict.parse(result.content)
    user_data = result_json["report"]["QueryResult"]["ResultXml"]["rowset"]["Row"]
    inactive_student_barcodes = [user["Column4"] for user in user_data]
    token = result_json["report"]["QueryResult"]["ResumptionToken"]
    is_finished = True if result_json["report"]["QueryResult"]["IsFinished"] == "true" else False

    # Fetch additional students using the resumption token
    while not is_finished:
        print("Fetching more students...")
        result = requests.get(
            f"https://api-na.hosted.exlibrisgroup.com/almaws/v1/analytics/reports?path=/shared/University of Maryland Global Campus (UMGC) 01USMAI_UMGC/Reports/Inactive Students&limit=1000&token={token}",
            headers={"Authorization": f"apikey {API_KEY}"})
        result_json = xmltodict.parse(result.content)
        user_data = result_json["report"]["QueryResult"]["ResultXml"]["rowset"]["Row"]
        additional_barcodes = [user["Column4"] for user in user_data]
        token = result_json["report"]["QueryResult"].get("ResumptionToken")
        is_finished = True if result_json["report"]["QueryResult"]["IsFinished"] == "true" else False
        inactive_student_barcodes.extend(additional_barcodes)

    print(f"Found {len(inactive_student_barcodes)} students.")
    if len(inactive_student_barcodes) > 1500:
        print("This may take some time, as it must be done in chunks...")

    # 2 - Create a set for the inactive students
    set_name = f"Inactive Students as of {datetime.now().strftime('%m/%d/%Y %H:%M:%S')}"
    set_body = {
        "link": "",
        "name": set_name,
        "description": "",
        "content": {
            "value": "USER",
        },
        "type": {
            "value": "ITEMIZED",
        },
        "private": {
            "value": "true",
        }
    }
    set_result = requests.post(f"https://api-na.hosted.exlibrisgroup.com/almaws/v1/conf/sets/",
                               headers={"Authorization": f"apikey {API_KEY}",
                                        "Accept": "application/json"},
                               json=set_body)
    set_url = set_result.json()["link"]
    set_id = set_result.json()["id"]

    # 3 - Add students to set

    # Break up chunks (Alma API can only handle 1000 in a single request)
    chunk_size = 750
    chunks = [inactive_student_barcodes[i:i + chunk_size] for i in range(0, len(inactive_student_barcodes), chunk_size)]

    # Add Members to Set
    for chunk in chunks:
        print(f"Adding {len(chunk)} students to set")
        # 3 - Add Members to Set
        set_body = {
            "content": {
                "value": "USER",
            },
            "type": {
                "value": "ITEMIZED",
            },
            "members": {
                "total_record_count": len(chunk),
                "member": [
                    {
                        "link": "",
                        "id": user_id
                    } for user_id in chunk
                ]
            }
        }
        add_members_result = requests.post(f"{set_url}?op=add_members", json=set_body,
                                           headers={"Authorization": f"apikey {API_KEY}",
                                                    "Accept": "application/json",
                                                    "Content-Type": "application/json"}
                                           )
        if add_members_result.status_code != 200:
            print("Error adding some students to set.")
            return None
    return set_id

last_day_of_prev_month = date.today().replace(day=1) - timedelta(days=1)
dt = datetime(last_day_of_prev_month.year, last_day_of_prev_month.month, last_day_of_prev_month.day)
time_millis = int(dt.timestamp() * 1000)


def run_employee_job(set_id):
    print("Running job on employees in 15 seconds. Press ctrl-c to cancel.")
    time.sleep(15)
    body = {
        "parameter": [{
            "name": {
                "value": "UPDATE_User_Information_AddBlock_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DontGeneratePassword_Value"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableBlock_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddRole_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Title_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Opt_Out_Patron_Letters_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableSMS_Value"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_SetAccountTo_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "SEND_Notification_To_User_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_CatalogerLevel_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRole_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_JobDescription_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Status_Active"
            },
            "value": "true"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRole_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddNote_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "PRODUCT"
            },
            "value": "alma"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Opt_In_Patron_Letters_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_JobDescription_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddNote_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveStatistics_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Status_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_FieldType_Value"
            },
            "value": "BY_USER_ACCOUNT_TYPE"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddStatistics_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddRole_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_ExportToCloudIdP_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Status_Value"
            },
            "value": "INACTIVE"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableBlock_Value"
            },
            "value": "02-GLOBAL"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddStatistics_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RSL_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddStatistics_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Opt_In_Patron_Letters_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Expiry_Date_Active"
            },
            "value": "true"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Expiry_Date_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddBlock_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveStatistics_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Opt_Out_Patron_Letters_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddNote_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_CatalogerLevel_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddRole_Value"
            },
            "value": "56"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Campus_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_UserGroup_Value"
            },
            "value": "ADMIN"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Purge_Date_Value"
            },
            "value": time_millis
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddRole_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Purge_Date_Active"
            },
            "value": "true"
        }, {
            "name": {
                "value": "SEND_Notification_To_User_Value"
            },
            "value": "SOCIAL_LOGIN_INVITAION"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Title_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_SetAccountTo_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableBlock_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_JobDescription_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_RSL_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_Title_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_UserGroup_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRole_Value"
            },
            "value": "56"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRole_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Campus_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddStatistics_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_ExportToCloudIdP_Value"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Expiry_Date_Value"
            },
            "value": time_millis
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddNote_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableSMS_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRSL_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DontGeneratePassword_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_UserGroup_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveStatistics_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRSL_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_Purge_Date_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddBlock_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddBlock_Value"
            },
            "value": "02-GLOBAL"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableBlock_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Campus_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "set_id"
            },
            "value": set_id
        }, {
            "name": {
                "value": "job_name"
            },
            "value": f"Update/Notify Users - via API - set {set_id}"
        }]
    }

    url = f"https://api-na.hosted.exlibrisgroup.com/almaws/v1/conf/jobs/M148?op=run"
    response = requests.post(url, headers={"Authorization": f"apikey {API_KEY}",
                                           "Accept": "application/json",
                                           "Content-Type": "application/json"},
                             json=body)

    if response.status_code == 200:
        print(f"Started job with ID {response.json().get('id')}")
    else:
        print(f"Error starting Employees job: {response.json()}")


def run_student_job(set_id):
    print("Running job on students in 15 seconds. Press ctrl-c to cancel.")
    time.sleep(15)
    body = {
        "parameter": [{
            "name": {
                "value": "UPDATE_User_Information_AddBlock_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DontGeneratePassword_Value"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableBlock_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddRole_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Title_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Opt_Out_Patron_Letters_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableSMS_Value"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_SetAccountTo_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "SEND_Notification_To_User_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_CatalogerLevel_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRole_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_JobDescription_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Status_Active"
            },
            "value": "true"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRole_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddNote_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "PRODUCT"
            },
            "value": "alma"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Opt_In_Patron_Letters_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_JobDescription_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddNote_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveStatistics_Value"
            },
            "value": "AL"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Status_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_FieldType_Value"
            },
            "value": "BY_USER_ACCOUNT_TYPE"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddStatistics_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddRole_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_ExportToCloudIdP_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Status_Value"
            },
            "value": "INACTIVE"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableBlock_Value"
            },
            "value": "02-GLOBAL"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddStatistics_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RSL_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddStatistics_Value"
            },
            "value": "AL"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Opt_In_Patron_Letters_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Expiry_Date_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Expiry_Date_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddBlock_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveStatistics_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Opt_Out_Patron_Letters_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddNote_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_CatalogerLevel_Value"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddRole_Value"
            },
            "value": "56"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Campus_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_UserGroup_Value"
            },
            "value": "11"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Purge_Date_Value"
            },
            "value": "0"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddRole_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Purge_Date_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "SEND_Notification_To_User_Value"
            },
            "value": "SOCIAL_LOGIN_INVITAION"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Title_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_SetAccountTo_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableBlock_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_JobDescription_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_RSL_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_Title_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_UserGroup_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRole_Value"
            },
            "value": "56"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRole_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Campus_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddStatistics_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_ExportToCloudIdP_Value"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Expiry_Date_Value"
            },
            "value": "0"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddNote_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableSMS_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRSL_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DontGeneratePassword_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_UserGroup_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveStatistics_Scope"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_RemoveRSL_Value"
            },
            "value": ""
        }, {
            "name": {
                "value": "UPDATE_User_Information_Purge_Date_Condition"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddBlock_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "UPDATE_User_Information_AddBlock_Value"
            },
            "value": "02-GLOBAL"
        }, {
            "name": {
                "value": "UPDATE_User_Information_DisableBlock_Scope_Name"
            },
            "value": "Null"
        }, {
            "name": {
                "value": "UPDATE_User_Information_Campus_Active"
            },
            "value": "false"
        }, {
            "name": {
                "value": "set_id"
            },
            "value": set_id
        }, {
            "name": {
                "value": "job_name"
            },
            "value": "Update/Notify Users - via API - Set Students Inactive"
        }]
    }

    url = f"https://api-na.hosted.exlibrisgroup.com/almaws/v1/conf/jobs/M148?op=run"
    response = requests.post(url, headers={"Authorization": f"apikey {API_KEY}",
                                           "Accept": "application/json",
                                           "Content-Type": "application/json"},
                             json=body)

    if response.status_code == 200:
        print(f"Started job with ID {response.json().get('id')}")
    else:
        print(f"Error starting Student job: {response.json()}")


def main():
    should_start_job = check_valid_status()

    if not should_start_job:
        print("Configuration invalid or status has not been updated. Goodbye!")
        return -1
    else: print("User checks out... starting set creation.")

    employee_set_id = create_employee_set()
    student_set_id = create_student_set()

    if RUN_JOBS:
        print("Running jobs...")
        if employee_set_id:
            run_employee_job(employee_set_id)
        else: print("Employee set cannot be created, so employee job will not run.")
        if student_set_id:
            run_student_job(student_set_id)
        else:
            print("Student set cannot be created, so student job will not run.")
    else:
        print("Job Running Off. You may view the sets in Alma - note you will need to delete \
them if you want to run this again on the same day")

    return 0


if __name__ == "__main__":
    main()