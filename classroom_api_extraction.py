import os
import json
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.course-work.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

def authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("classroom", "v1", credentials=creds)


def parse_due_datetime(coursework):
    if "dueDate" not in coursework:
        return None

    date = coursework["dueDate"]
    time = coursework.get("dueTime", {"hours": 23, "minutes": 59})

    return datetime(
        date["year"],
        date["month"],
        date["day"],
        time.get("hours", 0),
        time.get("minutes", 0)
    )


def extract_classroom_data(service):
    courses = service.courses().list(courseStates=["ACTIVE"]).execute().get("courses", [])

    extracted = []

    for course in courses:
        course_id = course["id"]

        section = course.get("section", "")
        name = course.get("name", "")

        if not (
            section == "Sem : IV :  CSE : I"
            or "open elective" in section.lower()
            or name.lower().startswith("oe")
        ):
            continue

        print(f"\n📘 Course: {name}")

        announcements = service.courses().announcements().list(
            courseId=course_id
        ).execute().get("announcements", [])

        materials = service.courses().courseWorkMaterials().list(
            courseId=course_id
        ).execute().get("courseWorkMaterial", [])

        coursework_items = service.courses().courseWork().list(
            courseId=course_id
        ).execute().get("courseWork", [])

        extracted.append({
            "course": course,
            "announcements": announcements,
            "materials": materials,
            "coursework": coursework_items
        })

        print(f"  Announcements: {len(announcements)}")
        print(f"  Materials: {len(materials)}")
        print(f"  Coursework items: {len(coursework_items)}")

        for cw in coursework_items:
            due = parse_due_datetime(cw)
            print(f"   📝 {cw['title']} | Due: {due}")

    return extracted



def main():
    service = authenticate()
    data = extract_classroom_data(service)

    with open("classroom_dump.json", "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(" Data saved to classroom_dump.json")



if __name__ == "__main__":
    main()
