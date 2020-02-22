import requests
import re
from bs4 import BeautifulSoup
from bs4.element import Tag

def split_weekdays(html_soup):
    delimiters = html_soup.select('td.delimiter')
    delimiters = [d.previous for d in delimiters]
    next_row = delimiters[0]

    days = {i:[] for i in range(7)}
    weekday = 0

    while next_row is not delimiters[-1]:
        next_row = next_row.next_sibling
        if next_row in delimiters: 
            weekday+=1 # Увеличение дня недели при нахождении разделителя дней недели
            if weekday >= 7: raise EOFError('Weekday>7??') # Если дней больше семи, то мы где-то сломались
            continue   # Разделители не участвуют в расписании

        # Пропускаем строки вне тегов (например, переносы строк \n)
        if next_row.name != 'tr': continue

        days[weekday].append(next_row)

    return days

def linearize(soup_arr):
    return re.sub(r' +', ' ', (' '.join([re.sub(r'<.*?>', ' ', str(a).replace('\xa0', ' ')) for a in soup_arr])).strip())

def parse_tditem_table(tditem_table_soup):
    return [linearize(i.contents) for i in tditem_table_soup.select('td')]

def parse_tditem(tditem_soup):    
    subject = []
    if len(tditem_soup.select('table')) > 0:
        subject.extend(parse_tditem_table(tditem_soup.select('table')[0]))
    else:
        subject = linearize(tditem_soup.contents)
            
    return subject

def parse_row(row_soup):
    time = row_soup.select('td.tdtime')

    if len(time) > 1: raise AttributeError('Too many time tags in row')
    elif len(time) < 1: time = None
    else: time = (time[0].contents[0], time[0].contents[-1])
    
    # Еженедельный предмет td.tditem1
    # Предмет только по четным (если время == None) или нечетным (иначе) неделям td.tdsmall1
    subject = row_soup.select('td.tditem1, td.tdsmall1')
    if len(subject) > 1: raise AttributeError('Too many subject tags in row')
    elif len(subject) < 1: subject = None
    else: 
        subject = parse_tditem(subject[0])
    
    return {
        'time': time,
        'subject': subject
    }

def parse_weekday(day_soup, day):
#     display(day_soup)
    return [parse_row(soup) for soup in day_soup]

def parse_week(soup):
    return {day: parse_weekday(soup, day) for day, soup in split_weekdays(soup).items()}

def parse_groupnums(soup):
    groups = []
    for num_str in soup.select('.tdheader a>b'): 
        groups.extend(re.findall(r'\d\d\d[MmМм]?', str(num_str)))
        
    return groups

def get_soup(grade, stream, group):
    user_agent = 'Mozilla/5.0 (Linux; Android 7.0; SM-G930V Build/NRD90M) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.125 Mobile Safari/537.36'
    headers = {'User-Agent': user_agent}
    response = requests.get(f'http://ras.phys.msu.ru/table/{grade}/{stream}/{group}.htm', headers=headers)
    
    if 'НЕТ ДАННЫХ' in response.text.upper():
        raise ConnectionError(404)
        
    if response.status_code != 200: 
        raise ConnectionError(response.status_code)

    return BeautifulSoup(response.text, 'lxml')

def split_subject(subject_str):
    subject_dict = {}
    
    group = re.findall(r'\d\d\d[^\.\, ]?', subject_str)
    if len(group)==1: 
        subject_dict['group'] = group[0]
    elif len(group) > 1:
        subject_dict['group'] = group
        
    room = re.findall(r'[А-Яа-яЁёA-Za-z0-9]-\d\d|каф|Л.каб.', subject_str, re.IGNORECASE)
    if len(room)==1: subject_dict['room'] = room[0]
    
    name_regexp = r'^(.*[^\.\,]? - )?(.*)'
    if len(room)==1: name_regexp += room[0] + '.*'
    name_regexp += '$'
    name = re.sub(name_regexp, 
                  r'\2',
                  subject_str, 
                  0,
                  re.IGNORECASE).strip()
    subject_dict['name'] = name
    
    teacher_regexp = '^.*'
    if len(room)==1: teacher_regexp += room[0]
    else: teacher_regexp += name
    teacher_regexp += '(.*)$'
    
    teacher = re.sub(teacher_regexp, 
                     r'\1',
                     subject_str, 
                     0,
                     re.IGNORECASE).strip()
    teacher = re.sub(r'([A-Za-zА-Яа-яЁё]\.\s?[A-Za-zА-Яа-яЁё]\.)\s?[^$]', r'\1~~~~', teacher, 1).split('~~~~')
    if len(teacher)==1: teacher = teacher[0]
    if len(teacher) > 0: subject_dict['teacher'] = teacher 
    
    for i in subject_dict.keys(): 
        subject_dict[i] = subject_dict[i][0] if len(subject_dict[i])==1 else subject_dict[i]
    
    return subject_dict

def normalize(timetable, groups):
    return timetable

def get_timetable(grade, stream, group):
    soup = get_soup(grade, stream, group)
    return normalize(parse_week(soup), parse_groupnums(soup))

