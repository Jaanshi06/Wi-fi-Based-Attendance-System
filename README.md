💻 Wi-Fi Based Automated Attendance System


A smart, fully-automated attendance system built using Python, Streamlit, and MySQL that detects students' presence through their Wi-Fi MAC addresses and marks attendance automatically — eliminating manual roll calls, reducing errors, and improving efficiency.

🚀 Features


🔍 Automatic Wi-Fi Network Scan

🆔 MAC Address Based Identification

👨‍🏫 Teacher & Subject Management

📋 Real-Time Attendance Dashboard

🎓 Student Management (Add / Edit / Delete)

📅 Daily & Monthly Attendance Tracking

📊 Excel Export (Teacher-wise, Month-wise)

⚡ Prevents Duplicate Attendance

🛠 Manual Override: Mark Present / Absent

🪪 Admin-Friendly Streamlit Interface

🗄 MySQL Database Integration

🧠 How It Works


Students connect their devices to the classroom Wi-Fi / Hotspot.

System runs OS-level command arp -a to fetch the list of connected devices.

Python extracts and normalizes MAC addresses using regex.

MAC addresses are matched with the MySQL Student Database.

On match → Attendance is automatically marked as Present.

A clean Streamlit UI displays real-time attendance status.

Teachers can export Excel sheets for any month & subject.

🏗 Project Architecture


📡 Wi-Fi Hotspot / Router → Detects connected devices

🖥 Python Script → Scans ARP table & extracts MACs

🛢 MySQL Database → Stores students, teachers, attendance logs

🌐 Streamlit Web App → User interface for teachers/admin

📁 Excel Reports → Generated using Pandas + Openpyxl

🛠 Tech Stack

Backend

Python 3.x

MySQL

pandas

mysql.connector

openpyxl

datetime, regex, subprocess, os

Frontend

Streamlit (Interactive Web UI)

System Commands

arp -a to detect Wi-Fi connected devices

🔮 Future Enhancements


📱 Mobile App + GPS Verification

🛰 Device Fingerprinting (Fix MAC Randomization)

📡 Router API Integration

🤖 AI-Based Attendance Trend Analysis

📊 Advanced Admin Dashboard

🔐 Anti-Spoofing Security Layer


<img width="942" height="462" alt="Screenshot 2025-11-23 184150" src="https://github.com/user-attachments/assets/7de8ec58-17b3-482c-b7d0-25ced59287a6" />

<img width="923" height="270" alt="Screenshot 2025-11-23 184239" src="https://github.com/user-attachments/assets/b651174d-60c3-48a8-a032-548cf45cf19b" />

