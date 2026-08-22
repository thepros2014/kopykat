with open('frontend/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

start = text.find('id="how"')
if start != -1:
    end = text.find('</section>', start)
    print(text[start-50:end+10])
