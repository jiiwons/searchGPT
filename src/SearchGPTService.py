import os

import pandas as pd
import yaml

from FrontendService import FrontendService
from LLMService import LLMServiceFactory
from SemanticSearchService import BatchOpenAISemanticSearchService
from SourceService import SourceService
from Util import setup_logger, get_project_root, storage_cached
from website.sender import Sender

logger = setup_logger('SearchGPTService')


class SearchGPTService:
    """
    SearchGPT app->service->child-service structure
    - (Try to) app import service, child-service inherit service

    SearchGPT class
    - SourceService
    -- BingService
    -- Doc/PPT/PDF Service
    - SemanticSearchModule
    - LLMService
    -- OpenAIService
    -- GooseAPIService
    - FrontendService

    """

    def __init__(self, ui_overriden_config=None, sender: Sender = None):
        with open(os.path.join(get_project_root(), 'src/config/config.yaml'), encoding='utf-8') as f:
            self.config = yaml.load(f, Loader=yaml.FullLoader)
        self.overide_config_by_query_string(ui_overriden_config)
        self.validate_config()
        self.sender = sender

    # 사용자 인터페이스에서 오버라이드된 설정 값을 config에 적용
    # ui_overriden_config: 사용자 인터페이스에서 오버라이드된 설정 값
    def overide_config_by_query_string(self, ui_overriden_config):
        if ui_overriden_config is None:
            return
        # 사용자 인터페이스에서 오버라이드된 설정 값들을 순회하면서 config에 적용
        for key, value in ui_overriden_config.items():
            if value is not None and value != '':
                # query_string is flattened (one level) while config.yaml is nested (two+ levels)
                # Any better way to handle this?
                if key == 'bing_search_subscription_key':
                    self.config['source_service']['bing_search']['subscription_key'] = value
                elif key == 'openai_api_key':
                    self.config['llm_service']['openai_api']['api_key'] = value
                elif key == 'is_use_source':
                    self.config['source_service']['is_use_source'] = False if value.lower() in ['false', '0'] else True
                elif key == 'llm_service_provider':
                    self.config['llm_service']['provider'] = value
                elif key == 'llm_model':
                    if self.config['llm_service']['provider'] == 'openai':
                        self.config['llm_service']['openai_api']['model'] = value
                    elif self.config['llm_service']['provider'] == 'goose_ai':
                        self.config['llm_service']['goose_ai_api']['model'] = value
                    else:
                        raise Exception(f"llm_model is not supported for llm_service_provider: {self.config['llm_service']['provider']}")
                elif key == 'language':
                    self.config['general']['language'] = value
                else:
                    # invalid query_string but not throwing exception first
                    pass

    # 설정 값의 유효성을 검사
    def validate_config(self):
        if self.config['source_service']['is_enable_bing_search']:
            assert self.config['source_service']['bing_search']['subscription_key'], 'bing_search_subscription_key is required'
        if self.config['llm_service']['provider'] == 'openai':
            assert self.config['llm_service']['openai_api']['api_key'], 'openai_api_key is required'

    # 검색 질의를 수행하고 답변을 가져옴
    @storage_cached('web', 'search_text')
    def query_and_get_answer(self, search_text):
        source_module = SourceService(self.config, self.sender) # SourceService 객체 생성
        bing_text_df = source_module.extract_bing_text_df(search_text) # Bing에서 텍스트 데이터 프레임을 추출
        doc_text_df = source_module.extract_doc_text_df(bing_text_df) # 문서에서 텍스트 데이터 프레임을 추출
        text_df = pd.concat([bing_text_df, doc_text_df], ignore_index=True) # Bing과 문서에서 추출한 텍스트 데이터 프레임을 합친다.

        semantic_search_service = BatchOpenAISemanticSearchService(self.config, self.sender) # BatchOpenAISemanticSearchService 객체를 생성
        gpt_input_text_df = semantic_search_service.search_related_source(text_df, search_text) # 관련 소스를 검색하고 GPT 입력 텍스트 데이터 프레임을 가져옴
        gpt_input_text_df = BatchOpenAISemanticSearchService.post_process_gpt_input_text_df(gpt_input_text_df,
                                                                                            self.config.get('llm_service').get('openai_api').get('prompt').get('prompt_token_limit')) # GPT 입력 텍스트 데이터 프레임을 후처리

        llm_service = LLMServiceFactory.create_llm_service(self.config, self.sender) # LLMService 객체를 생성
        prompt = llm_service.get_prompt_v3(search_text, gpt_input_text_df) # 검색 질의에 대한 프롬프트를 생성
        response_text = llm_service.call_api(prompt=prompt)  # LLM API를 호출하여 응답 텍스트를 가져옴

        frontend_service = FrontendService(self.config, response_text, gpt_input_text_df) # FrontendService 객체를 생성
        source_text, data_json = frontend_service.get_data_json(response_text, gpt_input_text_df)

        print('===========Prompt:============')
        print(prompt)
        print('===========Search:============')
        print(search_text)
        print('===========Response text:============')
        print(response_text)
        print('===========Source text:============')
        print(source_text)

        return response_text, source_text, data_json
