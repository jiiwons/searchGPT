import gradio as gr

from SearchGPTService import SearchGPTService

# 사용자가 입력한 검색 텍스트를 받아 SearchGPTService 클래스를 통해 처리한 후, 응답 텍스트와 출처 텍스트를 반환
def query_and_get_answer(search_text):
    search_gpt_service = SearchGPTService()
    response_text, source_text, data_json = search_gpt_service.query_and_get_answer(search_text)
    return response_text, source_text


demo = gr.Interface(fn=query_and_get_answer,
                    inputs=gr.Textbox(placeholder="What is chatgpt"),
                    outputs=["text", "text", "text"])
demo.launch()
