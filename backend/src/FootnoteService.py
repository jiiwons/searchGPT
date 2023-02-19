import nltk
import pandas as pd
import pyterrier as pt

from PyTerrierService import PyTerrierService


class FootnoteService:
    def __init__(self, config, response_text, gpt_input_text_df, pyterrier_service: PyTerrierService):
        self.config = config
        self.response_text = response_text
        used_columns = ['docno', 'name', 'url', 'url_id', 'text', 'len_text', 'is_used']  # TODO: add url_id
        self.gpt_input_text_df = gpt_input_text_df[used_columns]
        self.pyterrier_service = pyterrier_service

        if not pt.started():
            pt.init()

    def extract_sentences_from_paragraph(self):
        # TODO: currently only support English
        sentences = nltk.sent_tokenize(self.response_text)
        response_df = pd.DataFrame(sentences, columns=['response_text_sentence'])
        return response_df

    def get_footnote_from_sentences(self) -> list:
        response_sentences_df = self.extract_sentences_from_paragraph()
        in_scope_source_df = self.gpt_input_text_df[self.gpt_input_text_df['is_used']]
        source_indexref = self.pyterrier_service.index_text_df(in_scope_source_df, 'source_index')

        footnote_result_list = []
        for index, row in response_sentences_df.iterrows():
            response_text_sentence = row["response_text_sentence"]
            # print(f'[S{index + 1}] {response_text_sentence}')

            cleaned_response_text_sentence = self.pyterrier_service.clean_sentence_to_avoid_lexical_error(response_text_sentence)
            result_df = pt.BatchRetrieve(source_indexref).search(cleaned_response_text_sentence)
            result_df = result_df.merge(in_scope_source_df, on="docno", how="left")[['docid', 'rank', 'score', 'url', 'url_id', 'text']]

            SCORE_THRESHOLD = 5
            result_within_scope_df = result_df[result_df['score'] >= SCORE_THRESHOLD]

            footnote_result_sentence_dict = {
                'sentence': response_text_sentence,
                'url_unique_ids': sorted(result_within_scope_df['url_id'].unique().tolist()),
                'url_ids': result_within_scope_df['url_id'].tolist(),
                'source_sentence': result_within_scope_df['text'].tolist()
            }
            footnote_result_list.append(footnote_result_sentence_dict)
        return footnote_result_list

    def pretty_print_footnote_result_list(self, footnote_result_list):
        for footnote_result in footnote_result_list:
            footnote_print = ''
            for url_id in footnote_result['url_unique_ids']:
                footnote_print += f'[{url_id}]'
            print(f'{footnote_result["sentence"]}{footnote_print}')
