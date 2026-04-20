with open('templates/production/attendance_entry_form.html', 'r') as f:
    content = f.read()

content = content.replace('<select name="section" >', '<select name="section" hx-get="{% url \'production:attendance-entry\' %}" hx-target="body">')
content = content.replace('<input type="date" name="attendance_date" value="{{ attendance_date|date:\'Y-m-d\' }}" >', '<input type="date" name="attendance_date" value="{{ attendance_date|date:\'Y-m-d\' }}" hx-get="{% url \'production:attendance-entry\' %}" hx-target="body">')

with open('templates/production/attendance_entry_form.html', 'w') as f:
    f.write(content)
