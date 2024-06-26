
import transformers
import torch
import os
import tqdm
import json
import sys
from utils import log_method,ClearCache,load_tokenizer,load_model_with_adapters, read_json, write_json,split_into_batches
from transformers import StoppingCriteria,StoppingCriteriaList
from torch import LongTensor, FloatTensor


def inference(model, tokenizer, batch_input_text,stopping_criteria):
    input_ids = tokenizer(batch_input_text, return_tensors="pt", padding=True, truncation=True).to('cuda:0')
    with torch.no_grad():
        outputs = model.generate(
            input_ids=input_ids['input_ids'], 
            do_sample=True, 
            use_cache=True, 
            num_return_sequences=1,
            max_new_tokens=100,
            temperature=0.3,
            attention_mask=input_ids['attention_mask'] ,
            pad_token_id=tokenizer.pad_token_id,
            stopping_criteria=stopping_criteria
        )
    #generated_texts = [tokenizer.decode(each, skip_special_tokens=True) for each in outputs]
    torch.cuda.empty_cache()
    res = [tokenizer.decode(each, skip_special_tokens=True) for each in outputs]
    del input_ids
    return res



@log_method
def answer_inference():
    arguments = json.loads(sys.argv[1])
    iteration = int(arguments['cur_iteration'])
    adapters_path = arguments['adapters_path']
    model_path = arguments['model_path']
    answer_prompts_path = arguments['answer_prompts_path']
    answer_dataset_path = arguments['answer_dataset_path']
    inference_batch_size =int(arguments['inference_batch_size'])

    with ClearCache():
        answer_data = read_json(answer_prompts_path)

        tokenizer = load_tokenizer(model_path)
        stop_list = [" \n\n", "\n\n"]
        stop_token_ids = [tokenizer(x, return_tensors='pt', add_special_tokens=False)['input_ids'] for x in stop_list]
        stop_token_ids = [LongTensor(x).to('cuda:0') for x in stop_token_ids]
        class StopOnTokens(StoppingCriteria):
            def __call__(self, input_ids: LongTensor, scores: FloatTensor, **kwargs) -> bool:
                for stop_ids in stop_token_ids:
                    if (input_ids[0][-len(stop_ids[0])+1:] == stop_ids[0][1:]).all():
                        return True
                return False
        stopping_criteria = StoppingCriteriaList([StopOnTokens()])
        model = load_model_with_adapters(iteration, adapters_path, model_path)
        model.eval() 

        texts = []
        print("texts",len(texts))
        index_dict = []
        for key, value in answer_data.items():
            texts += value['Answer Prediction Prompt Dataset']
            for each_instance_idx in range(len(value['Instances'])):
                index_dict.append((key, each_instance_idx))

            assert len(value['Answer Prediction Prompt Dataset']
                    ) == len(value['Instances'])

        result = []
        batches = split_into_batches(texts, inference_batch_size)
        for each_batch in tqdm.tqdm(batches):


            res = inference(model, tokenizer, each_batch,stopping_criteria)

            for idx, each_output in enumerate(res):
                    
                output_text = each_output[len(each_batch[idx]):]
                truncated_result = output_text.strip()

                result.append(truncated_result)

        for i, text in enumerate(texts):
            task, index = index_dict[i]
            # Write answer prediction to json file.
            answer_data[task]["Instances"][index]['answer_prediction'] = result[i]

        del result,texts,index_dict

        write_json(answer_dataset_path, answer_data)



answer_inference()