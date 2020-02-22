import requests
import re
from bs4 import BeautifulSoup
from bs4.element import Tag

def split_weekdays(html_soup):
    """Функция выделения из всего HTML кода страницы частей, содержащих расписание

    Производит поиск разделителей (строк таблицы с классом delimiter), которые 
    делят таблицу на заголовок, 6 дней недели, и подвал. Возвращает dict, 
    содержащий 7 дней недели (0 - понедельник), из списков BeautifulSoup-тегов 
    соответсвующих разным строкам таблицы расписания. 

    Ангрументы:
        html_soup: BeautifulSoup-преобразованная страница с расписанием 
        мобильной версии сайта

    Возвращаемое значение: 
        {
            0: [tags],
            1: [tags],
            2: [tags],
            3: [tags],
            4: [tags],
            5: [tags],
            6: [tags],
        }
    """
    # Находим все строки разделители (класс delimiter установлен у столбцов)
    delimiters = html_soup.select('td.delimiter')
    delimiters = [d.previous for d in delimiters]
    next_row = delimiters[0]

    # Инициализируем словарь для заполнения
    days = {i:[] for i in range(7)}
    weekday = 0

    # Пока не дошли до последнего разделителя (отделяющего субботу от подвала)
    # выполняй поисе строк с предметами
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
    """Функция для преобразования названия предмета из HTML в чистый текст

    Избавляет содержимое тега с названием предмета от лишних тегов и 
    специальных символов

    Аргументы:
        soup_arr: массив, представляющий содержимое тега с названием предмета
        может содержать строки или html теги

        Пример: 
            ['409, 411 - 414, 418, 438 - Численные методы в физике ',
             <nobr>5-18</nobr>,
             ' проф.\xa0Галкин\xa0В.\xa0И.']

    Возвращаемое значение:
        Одна строка - название предмета (возможно, содержащее номера групп, 
        кабинет и ФИО преподавателя)
        
        Пример:
            '409, 411 - 414, 418, 438 - Численные методы в физике 5-18 проф. Галкин В. И.'

    """
    return re.sub(r' +', 
                  r' ',
                  (' '.join([
                      re.sub(r'<.*?>', 
                             r' ', 
                             str(a).replace('\xa0', ' ')
                      ) for a in soup_arr]
                  )).strip()
    )

def parse_tditem_table(tditem_table_soup):
    """Преобразует внутренности ячейки предмета, если они представлены таблицей
    
    Такое происходит в случаях, когда разные кафедры имеют разные спецкурсы или 
    английский у разных групп ведут разные преподаватели в разынх кабинетах.
    """
    return [linearize(i.contents) for i in tditem_table_soup.select('td')]

def parse_tditem(tditem_soup):
    """Преобразует ячейку с названием предмета в массив предметов в строковом виде

    Аргументы:
        row_soup: BeautifulSoup-тег td, содержащий название предмета 
        (td.tditem1 / td.tdsmall1)

    Возвращаемое значение: 
        Название предмета (str) или массив (list) названий предмета
    """ 
    subject = []
    if len(tditem_soup.select('table')) > 0:
        subject.extend(parse_tditem_table(tditem_soup.select('table')[0]))
    else:
        subject = linearize(tditem_soup.contents)
            
    return subject

def parse_row(row_soup):
    """Преобразует строку с предметом в словарь из времени начала-окончания и 
    названия предмета

    Аргументы:
        row_soup: BeautifulSoup-тег tr, содержащий ячейки с временем (td.tdtime)
        и названием предмета (td.tditem1 / td.tdsmall1)

    Возвращаемое значение:
        Словарь с элементами 'time' и 'subject'. Первый содержит массив из двух 
        элементов: времени начала и окончания пары, а второй - строку или 
        массив из названий предметов, которые пройдут в это время. 
    """ 

    # Выделяет время, и записывает массив из начала и конца, если нашел.
    # Если не нашел - возвращает None (такое бывает у пар по четным неделям)
    # Иначе вызывает ошибку
    time = row_soup.select('td.tdtime')
    if len(time) > 1: raise AttributeError('Too many time tags in row')
    elif len(time) < 1: time = None
    else: time = (time[0].contents[0], time[0].contents[-1])
    
    # Выляет тег с временем и парсит его
    # Еженедельный предмет td.tditem1
    # Предмет только по четным или нечетным неделям td.tdsmall1
    subject = row_soup.select('td.tditem1, td.tdsmall1')
    if len(subject) > 1: raise AttributeError('Too many subject tags in row')
    elif len(subject) < 1: subject = None
    else: 
        subject = parse_tditem(subject[0])
    
    return {
        'time': time,
        'subject': subject
    }

def parse_weekday(day_soup):
    """Парсит список предметов на день
    
    Аргументы:
        day_soup: массив из BeautifulSoup-тегов строк, содержащих названия 
        предметов за сутки.

    Возвращаемое значение:
        Массив из предметов в словаря с элементами 'time' и 'subject' (см. parse_row)
    """
    return [parse_row(soup) for soup in day_soup]

def parse_week(soup):
    """Парсит список предметов на неделю

    Аргументы:
        soup: BeautifulSoup-преобразованная страница с расписанием 
        мобильной версии сайта

    Возвращаемое значение:
        Словарь из 7 элементов (0 - понедельник, 1 - вторник и т.д.), содержащий
        массивы из предметов в виде словарей с элементами 'time' и 'subject' 
        (см. parse_row)
    """
    return {day: parse_weekday(soup) for day, soup in split_weekdays(soup).items()}

def parse_groupnums(soup):
    """Парсит номера групп с сайта

    Аргументы:
        soup: BeautifulSoup-преобразованная страница с расписанием 
        мобильной версии сайта
    
    Возвращаемое значение:
        Массив из строковых представлений номеров групп

        Пример:
            ['409', '412', '418', '438']
            ['102M']
    """
    groups = []
    for num_str in soup.select('.tdheader a>b'): 
        groups.extend(re.findall(r'\d\d\d[MmМм]?', str(num_str)))
        
    return groups

def get_soup(grade, stream, group):
    """Получает определеннуб мобильную версию страницы сайта с расписанием 

    Делает запрос к странице http://ras.phys.msu.ru/table/{grade}/{stream}/{group}.htm
    с мобильным UserAgent. Поднимает ошибку ConnectionError, если на этой 
    странице нет расписания или сайт вернул любую HTTP ошибку. 

    Аргументы:
        grade, stream, group: курс, поток и номер страницы с расписанием 
        (для 1-2 курсов совпадает с номером группы)

    Возвращаемое значение:
        BeautifulSoup-преобразованная мобильная версия сайта с расписанием 
    """
    user_agent = 'Mozilla/5.0 (Linux; Android 7.0; SM-G930V Build/NRD90M) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.125 Mobile Safari/537.36'
    headers = {'User-Agent': user_agent}
    response = requests.get(f'http://ras.phys.msu.ru/table/{grade}/{stream}/{group}.htm', headers=headers)
    
    if 'НЕТ ДАННЫХ' in response.text.upper():
        raise ConnectionError(404)
        
    if response.status_code != 200: 
        raise ConnectionError(response.status_code)

    return BeautifulSoup(response.text, 'lxml')

def split_subject(subject_str):
    """Делит название предмета на группу, кабинет, преподавателя и название

    Аргументы:
        subject_str: строка с названием предмета

        Пример: '409, 411 - 414, 418, 438 - Численные методы в физике 5-18 проф. Галкин В. И.'

    Возвращаемое значение: 
        Словарь, содержащий название предмета и (опционально) номера групп, 
        кабинет и преподавателя

        Пример: {'group': ['409', '411', '414', '418', '438'],
                 'room': '5-18',
                 'name': 'Численные методы в физике',
                 'teacher': 'проф. Галкин В. И.'}

        Известные проблемы:
            * Если номер кабинета не указан, то преподаватель будет частью 
              названия предмета
            * Если преподавателей несколько, то они будут в виде одной строки, 
              а не в отдельных элементах массива
            * Кабинеты находятся только если они написаны в нумерации 
              физического факультета ('Ц-12', '5-51'), являются кафедрой ('Каф.') 
              или лингафонным кабинетом ('Л.каб.'). Такие номера как 'ГЗ-13эт.' 
              будут пропущены
    """
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

def normalize_timetable(timetable, groups):
    """TODO: Преобразует расписание одной страницы сайта к нормализованному виду

    Аргументы: 

    Возвращаемое значение:
        Нормализованный вид расписания на неделю:
        {
            '<Номер группы>': {
                'even': [
                    [
                        {
                            'begin': '<Время начала>',
                            'end': '<Время окончания>',
                            'name': '<Название предмета>',
                            'room': '<Номер кабинета>',
                            'teacher': '<Имя преподавателя>',
                        }
                    ],
                    [...],
                    [...],
                    [...],
                    [...],
                    [...],
                    [...],
                ],
                'odd': ... 
            },
            ...
        }
    """
    return timetable

def get_timetable(grade, stream, group):
    """Возвращает расписание с одной страницы

    Аргументы:
        grade, stream, group: курс, поток и номер страницы с расписанием 
        (для 1-2 курсов совпадает с номером группы)

    Возвращаемое значение:
        Преобразованное в dict расписание с сайта (см. normalize_timetable)
    """
    soup = get_soup(grade, stream, group)
    return normalize_timetable(parse_week(soup), parse_groupnums(soup))

