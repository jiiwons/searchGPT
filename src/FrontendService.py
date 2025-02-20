import os
import re
from urllib.parse import urlparse

import yaml

from NLPUtil import split_with_delimiters, get_longest_common_word_sequences
from Util import setup_logger, get_project_root

logger = setup_logger('FootnoteService')


class FrontendService:
    def __init__(self, config, response_text, gpt_input_text_df):
        self.config = config
        self.response_text = response_text
        used_columns = ['docno', 'name', 'url', 'url_id', 'text', 'len_text', 'in_scope']  # TODO: add url_id
        self.gpt_input_text_df = gpt_input_text_df[used_columns]

    # 설정 파일에서 프롬프트 예제 가져오기
    @staticmethod
    def get_prompt_examples_json():
        with open(os.path.join(get_project_root(), 'src/config/config.yaml'), encoding='utf-8') as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
            # 프롬프트 예제 데이터 추출
            col1_list = config['frontend_service']['prompt_examples']['col1_list']
            col2_list = config['frontend_service']['prompt_examples']['col2_list']
            prompt_examples_json = {
                'col1_list': col1_list,
                'col2_list': col2_list,
            }
            return prompt_examples_json

    # 응답 텍스트(response_text)와 GPT 입력 텍스트 데이터프레임(gpt_input_text_df)을 기반으로 데이터 JSON 생성
    def get_data_json(self, response_text, gpt_input_text_df):
        def create_response_json_object(text, type):
            return {"text": text, "type": type}

        def create_source_json_object(footnote, domain, url, title, text):
            return {"footnote": footnote, "domain": domain, "url": url, "title": title, "text": text}

        # 응답 텍스트에서 URL ID 재정렬
        def reorder_url_id(response_text, gpt_input_text_df):
            # response_text: find reference in text & re-order(응답 텍스트에서 URL ID 추출 및 정렬)
            url_id_list = [int(x) for x in dict.fromkeys(re.findall(r'\[([0-9]+)\]', response_text))]
            url_id_map = dict(zip(url_id_list, range(1, len(url_id_list) + 1)))

            # 응답 텍스트에서 URL ID를 재정렬된 값으로 변경
            response_text = re.sub(r'\[([0-9]+)\]', lambda x: f"[{url_id_map[int(x.group(1))]}]", response_text)
            # for multiple references in same sentence, sort as per url_id(여러 참조가 같은 문장에 있는 경우, URL ID 정렬)
            refs = set(re.findall(r'(\[[0-9\]\[]+\])', response_text))
            for ref in refs:
                response_text = response_text.replace(ref, '[' + ']['.join(sorted(re.findall(r'\[([0-9]+)\]', ref))) + ']')

            # gpt_input_text_df: find reference in text & re-order(데이터프레임에서 URL ID가 재정렬된 값으로 필터링 및 변경)
            in_scope_source_df = gpt_input_text_df[gpt_input_text_df['url_id'].isin(url_id_map.keys()) & gpt_input_text_df['in_scope']].copy()
            in_scope_source_df['url_id'] = in_scope_source_df['url_id'].map(url_id_map)
            return response_text, in_scope_source_df

        # 응답 텍스트에서 JSON 객체 생성
        def get_response_json(response_text):
            def create_response_json_object(text, type):
                return {"text": text, "type": type}

            response_json = []
            split_sentence = re.findall(r'\[[0-9]+\]|[^\[\]]+', response_text)

            components = []
            for component in split_sentence:
                components.extend(split_with_delimiters(component, ['\n']))
            for sentence in components:
                if sentence.startswith('[') and sentence.endswith(']'):
                    response_json.append(create_response_json_object(sentence, "footnote"))
                elif sentence == '\n':
                    response_json.append(create_response_json_object(sentence, "newline"))
                else:
                    response_json.append(create_response_json_object(sentence, "response"))
            # 예시
            # 참조: {"text": "[1]", "type": "footnote"}
            # 줄바꿈: {"text": "\n", "type": "newline"}
            # 응답: {"text": "This is a response text.", "type": "response"}
            return response_json

        def get_source_json(in_scope_source_df):
            # docno 컬럼의 데이터 타입 변환 및 정렬
            in_scope_source_df.loc[:, 'docno'] = in_scope_source_df['docno'].astype(int)
            in_scope_source_df.sort_values('docno', inplace=True)
            source_text_list = []
            source_json = []
            source_url_df = in_scope_source_df[['url_id', 'url', 'name', 'snippet']].drop_duplicates().sort_values('url_id').reset_index(drop=True)
            # 출처 정보 처리
            for index, row in source_url_df.iterrows():
                url_text = ''
                url_text += f"[{row['url_id']}] {row['url']}\n"

                for index, row in in_scope_source_df[in_scope_source_df['url_id'] == row['url_id']].iterrows():
                    url_text += f"  {row['text']}\n"

                source_text_list.append(url_text)

                domain_name = urlparse(row['url']).netloc.replace('www.', '')
                source_json.append(create_source_json_object(f"[{row['url_id']}]", domain_name, row['url'], row['name'], row['snippet']))
            source_text = ''.join(sorted(source_text_list))

            source_json = sorted(source_json, key=lambda x: x['footnote'])
            return source_json, source_text

        # 공통 단어 시퀀스를 기반으로 응답 텍스트와 소스 텍스트에 색상 코딩 적용
        def get_explainability_json(response_text, source_text):
            def get_colors():
                return ['#ffe3e8', '#f1e1ff', '#c5d5ff', '#c5efff', '#d6fffa', '#e7ffe7', '#f7ffa7', '#fff3b3', '#ffdfdf', '#ffcaca']

            def create_response_json_object(text, type, color):
                return {"text": text, "type": type, "color": color}

            def get_explain_json(text, word_color_dict):
                common_word_sequences = list(word_color_dict.keys())
                word_list = split_with_delimiters(text.lower(), common_word_sequences + ['\n'])
                explain_json = []
                for word in word_list:
                    if word == '\n':
                        explain_json.append(create_response_json_object(word, "newline", ""))
                    elif word.lower() in common_word_sequences:
                        explain_json.append(create_response_json_object(word, "keyword", word_color_dict[word.lower()]))
                    else:
                        explain_json.append(create_response_json_object(word, "word", ""))
                return explain_json

            longest_common_word_sequences = get_longest_common_word_sequences(response_text, source_text, k=10)
            word_color_dict = {longest_common_word_sequences[i]: get_colors()[i] for i in range(min(len(longest_common_word_sequences), len(get_colors())))}

            response_explain_json = get_explain_json(response_text, word_color_dict)
            source_explain_json = get_explain_json(source_text, word_color_dict)
            return response_explain_json, source_explain_json

        # URL ID 재정렬 및 데이터프레임 업데이트
        response_text, in_scope_source_df = reorder_url_id(response_text, gpt_input_text_df)
        # 응답 JSON 객체 생성
        response_json = get_response_json(response_text)
        # 소스 JSON 객체 생성
        source_json, source_text = get_source_json(in_scope_source_df)
        # 설명 가능성 JSON 객체 생성
        response_explain_json, source_explain_json = get_explainability_json(response_text, source_text)
        # 프롬프트 예제 JSON 객체 가져오기
        prompt_examples_json = FrontendService.get_prompt_examples_json()

        return source_text, {'response_json': response_json,
                             'source_json': source_json,
                             'response_explain_json': response_explain_json,
                             'source_explain_json': source_explain_json,
                             'prompt_examples_json': prompt_examples_json,
                             }


if __name__ == '__main__':
    # str_list = ['Alpaca lora',
    #             'what is new for gpt4?',
    #             'Why Llama LLM model is so popular?',
    #             'Why did SVB collapsed?',
    #             'End of FTX',
    #             'digital twin有哪些用处',
    #             '아가동산사건의 문제가 뭐야',
    #             'Hoe maak ik pasta',
    #             '日本国憲法は誰が作ったのか？',
    #             "Comment gagner de l'argent"]
    # for s in str_list:
    #     print(path_safe_string_conversion(s))

    import os
    import pickle

    folder_path = r""
    # 폴더 내 파일 목록 가져오기
    pickle_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path)]
    for file_path in pickle_files:
        if not '8d' in file_path:
            continue
        with open(file_path, "rb") as f:
            obj = pickle.load(f)
            print(file_path)
            print(obj['result'][0])
