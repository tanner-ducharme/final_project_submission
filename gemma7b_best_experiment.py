# -*- coding: utf-8 -*-
"""gemma7b - best experiment

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1ePBmQiahiacXzo4hI5zt6Ew2EnUTHb-a

# fine tuning gemma-7b on english-bengali parallel corpus
this notebook allows you to run our group's most successful experiment (in terms of BLEU score achieved)
To run it, you'll have to use your own huggingface token and mount the notebook to where it exists in your google drive. everythin else should work as is

### the first half of the notebook is for training the model
we exclusively used a V100 for training
### the second half is for generating predictions on the two test sets

#### install packages
"""



# """#### paste HF token"""

# from huggingface_hub import notebook_login
# 

# notebook_login()

# """#### mount drive

# """

# # Commented out IPython magic to ensure Python compatibility.
# from google.colab import drive
# drive.mount('/content/drive/')
# # %cd /content/drive/MyDrive/path/to/your/folder/

# import sys
# # If your Python files are in the 'part2' directory or a subdirectory of it, add 'part2' to the path
# sys.path.append('/content/drive/MyDrive/path/to/your/folder/')

"""#### this `exp_name` determines where the experimental results will be saved"""

exp_name = "gemma-7b-test"

"""#### *Import* all the necessary packages."""

from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, TrainingArguments
from peft import prepare_model_for_kbit_training, LoraConfig, get_peft_model
from datasets import load_dataset, concatenate_datasets
from trl import SFTTrainer
import torch

"""#### establish configs for quantization, load model and load the tokenizer"""

model_name = "google/gemma-7b"

compute_dtype = getattr(torch, "float16")
bnb_config = BitsAndBytesConfig(load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
)
model = AutoModelForCausalLM.from_pretrained(model_name,quantization_config=bnb_config, device_map={"": 0})
model = prepare_model_for_kbit_training(model)

tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True, add_eos_token=True)
tokenizer.pad_token = tokenizer.unk_token
tokenizer.padding_side = "left"

"""#### read training data from HF"""

raw_data = load_dataset("csebuetnlp/BanglaNMT")

"""#### get subset of data since we don't have the resources to train on the entire *dataset*

partition training and validation data
"""

# get 100_000 elements from raw_data
raw_data_train = raw_data['train'].select(range(10000)).shuffle(seed=42)

raw_data_valid = raw_data['validation']

def generate_prompt(data_point, instruction, source, target):
    """Gen. input text based on a prompt, task instruction, (context info.), and answer

    :param data_point: dict: Data point
    :return: dict: tokenzed prompt
    """

    text = f"""<start_of_turn>user
    {instruction}{data_point[source]}<end_of_turn>
    <start_of_turn>model
    {data_point[target]} <end_of_turn>
    """
    return text

"""#### code for adding bidirectional-translation data
this code adds examples of english to bengali data points and bengali to english datapoints to our training data <br>
### the hope is that the bidirectional data better allows the model to learn the relationship between the two languages
"""

instruction = "Translate the following Bengali text to English: "

train_dataset_bn_en = raw_data_train.map(lambda example: {'prompt':f"""<start_of_turn>user
{instruction}{example['bn']}<end_of_turn>
<start_of_turn>model
{example['en']} <end_of_turn>"""})

instruction = "Translate the following English text to Bengali: "

train_dataset_en_bn = raw_data_train.map(lambda example: {'prompt':f"""<start_of_turn>user
{instruction}{example['en']}<end_of_turn>
<start_of_turn>model
{example['bn']} <end_of_turn>"""})

combined_train_dataset = concatenate_datasets([train_dataset_bn_en, train_dataset_en_bn])
combined_train_dataset = combined_train_dataset.shuffle(seed=42)

"""pre-process validation data"""

instruction = "Translate the following Bengali text to English: "
valid_dataset = raw_data_valid.map(lambda example: {'prompt':f"""<start_of_turn>user
{instruction}{example['bn']}<end_of_turn>
<start_of_turn>model
{example['en']} <end_of_turn>"""})

valid_dataset['prompt'][0]

"""LoRA configuration:"""

peft_config = LoraConfig(
            lora_alpha=16,
            lora_dropout=0.05,
            r=16,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules= ["down_proj","up_proj","gate_proj"]
)

torch.cuda.empty_cache()

"""#### establish training arguments
this will save checkpoints in a "/results/exp_name/" folder
"""

training_arguments = TrainingArguments(
        output_dir=f"/results/{exp_name}",
        evaluation_strategy="steps",
        optim="paged_adamw_8bit",
        save_steps=500,
        log_level="debug",
        logging_steps=20,
        learning_rate=2e-5,
        eval_steps=100,
        fp16=True,
        do_eval=True,
        auto_find_batch_size=True,
        warmup_steps=100,
        max_steps=1000,
        lr_scheduler_type="linear"
)

"""#### create trainer"""

trainer = SFTTrainer(
        model=model,
        train_dataset=combined_train_dataset,
        eval_dataset=valid_dataset,
        peft_config=peft_config,
        dataset_text_field="prompt",
        max_seq_length=256,
        tokenizer=tokenizer,
        args=training_arguments
)

"""#### train"""

trainer.train()

"""# important
the remainder of the code is for loading the fine-tuned adapter weights, merging it with the baseline model, and generating predictions<br>
sometimes it is necessary to restart the kernel (for GPU reasons) in order to run this code. **If you are restarting the kernel, just make sure you re-mount your drive at the top.** Then the rest of this code can be executed

#### install packages
"""


"""#### import libraries"""

from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, GenerationConfig
import torch
from peft import PeftModel

"""make sure this is the same as the one used in the first half of the notebook"""

exp_name = "gemma-7b-test"

"""#### re-authenticate (if necessary)"""

# from huggingface_hub import notebook_login

# 

# notebook_login()

"""#### use the same parameters as before for loading and quantizing the base model"""

base_model = "google/gemma-7b"
compute_dtype = getattr(torch, "float16")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=compute_dtype,
    bnb_4bit_use_double_quant=True,
)
model = AutoModelForCausalLM.from_pretrained(
        base_model, device_map={"": 0}, quantization_config=bnb_config
)
tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True)

"""#### load test data"""

def read_sentences(file_path):
  with open(file_path, encoding='utf-8') as file:
      sentences = file.read().strip().split('\n')
  return sentences

def generate_eval_prompt(data_point, instruction, source):
    """Gen. input text based on a prompt, task instruction, (context info.), and answer

    :param data_point: dict: Data point
    :return: dict: tokenzed prompt
    """
    # print(instruction)
    # print(data_point)
    # print(source)

    text = f"""<start_of_turn>user
{instruction}{data_point}<end_of_turn>
<start_of_turn>model"""
    return text

"""### important:
make sure these files paths are correct for your drive set up (they should be good to go)
"""

source_lang = "bn"
target_lang = "en"


# get test data
supara_source_val_path = f"data/SUPara-benchmark/suparadev2018/suparadev_{source_lang}.txt"
supara_target_val_path = f"data/SUPara-benchmark/suparadev2018/suparadev_{target_lang}.txt"

rising_source_val_path = f"data/RisingNews-benchmark/RisingNews.valid.{source_lang}"
rising_target_val_path = f"data/RisingNews-benchmark/RisingNews.valid.{target_lang}"

# # read SUPara source language data
supara_source_val_raw = read_sentences(supara_source_val_path)
# # read SUPara target language data
supara_target_val = read_sentences(supara_target_val_path)

# # read SUPara source language data
rising_source_val_raw = read_sentences(rising_source_val_path)
# # read SUPara target language data
rising_target_val = read_sentences(rising_target_val_path)

"""#### prepend instructions and format test data into correct format"""

instruction = "Translate the following Bengali text into English:"

supara_source_val = [generate_eval_prompt(example, instruction, 'bn') for example in supara_source_val_raw]
rising_source_val = [generate_eval_prompt(example, instruction, 'bn') for example in rising_source_val_raw]


print("SUPara source validation sentence before and after system prompt:")
print(f"BEFORE:\n{supara_source_val_raw[0]}")
print(f"AFTER:\n{supara_source_val[0]}")

print("\nSUPara target language test sentence:")
print(supara_target_val[0])

print("\nRisingNews source validation sentence before and after system prompt:")
print(f"BEFORE:\n{rising_source_val_raw[0]}")
print(f"AFTER:\n{rising_source_val[0]}")



print("\nRisingNews target language test sentence:")
print(rising_target_val[0])

"""#### convert test data in to HF Dataset object"""

from datasets import Dataset
import pandas as pd

supara_df = pd.DataFrame({'source': supara_source_val, 'target': supara_target_val})
rising_df = pd.DataFrame({'source': rising_source_val, 'target': rising_target_val})


supara_dataset = Dataset.from_pandas(supara_df)
rising_dataset = Dataset.from_pandas(rising_df)
rising_dataset['source'][0]

"""#### load checkpoints <br>
for the best version of our experiment, we ran for 10000 iterations  <br>
since this notebook is just a proof-of-concept, we have it set to run for only 1000
"""

full_model = PeftModel.from_pretrained(model, f"results/{exp_name}/checkpoint-1000/")

del model

"""#### code for generating predictions
this code takes a long time to run <br>
in case of colab timeouts, I wrote it so that it saves every 100 predictions to a csv to prevent data loss
"""

from tqdm import tqdm
import pandas as pd
import torch
import re

num_predictions = len(rising_dataset['source'])

save_every_n = 100

# Assuming rising_dataset, tokenizer, and full_model are already defined
predictions = []

# Function to save dataframe
def save_dataframe(index):
    # Load existing data if it exists
    print(f"Saving dataframe for index {index}")
    try:
        df_existing = pd.read_csv(f"results/{exp_name}/gemma_7b_rising_preds.csv")
    except FileNotFoundError:
        df_existing = pd.DataFrame(columns=['source', 'target', 'prediction'])

    # Create new dataframe from current predictions
    df_new = pd.DataFrame({
        'source': rising_dataset['source'][index-save_every_n:index],
        'target': rising_dataset['target'][index-save_every_n:index],
        'prediction': predictions[-save_every_n:]
    })

    # Append new data and save
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    df_combined.to_csv(f"results/{exp_name}/gemma_7b_rising_preds.csv", index=False)

# Adjust for your needs

torch.cuda.empty_cache()
for i, source in enumerate(tqdm(rising_dataset['source'][:num_predictions])):
    torch.cuda.empty_cache()
    tokenized_input = tokenizer(source, return_tensors="pt")
    input_ids = tokenized_input["input_ids"].cuda()
    del tokenized_input
    generation_output = full_model.generate(
        input_ids=input_ids,
        num_beams=6,
        return_dict_in_generate=True,
        output_scores=True,
        max_new_tokens=130
    )
    del input_ids
    for seq in generation_output.sequences:
        output = tokenizer.decode(seq, skip_special_tokens=True)
        pattern = r'Translate the following Bengali text into English:.*?\nmodel\n(.*)'
        match = re.search(pattern, output, re.DOTALL)  # re.DOTALL allows '.' to match newlines as well

        if match:
            prediction = match.group(1).strip()  # .strip() to remove any leading or trailing whitespace
            print("Prediction:", prediction)
        else:
            print("No match found.")


        predictions.append(prediction)

    # Save every 100 predictions
    if (i + 1) % save_every_n == 0:
        save_dataframe(i + 1)
        print(f"\nSOURCE:\n{source}")
        print(f"PREDICTION:\n{prediction}")
        print(f"TARGET:\n{rising_dataset['target'][i]}\n\n")

torch.cuda.empty_cache()

# Save remaining predictions if there are any
if len(predictions) % 100 > 0:
    save_dataframe(len(predictions))

from tqdm import tqdm
import pandas as pd
import torch

# Adjust for your needs
num_predictions = len(supara_dataset['source'])

# Assuming rising_dataset, tokenizer, and full_model are already defined
predictions = []

# Function to save dataframe
def save_dataframe(index):
    # Load existing data if it exists
    print(f"Saving dataframe for index {index}")
    try:
        df_existing = pd.read_csv(f"results/{exp_name}/gemma_7b_supara_preds.csv")
    except FileNotFoundError:
        df_existing = pd.DataFrame(columns=['source', 'target', 'prediction'])

    # Create new dataframe from current predictions
    df_new = pd.DataFrame({
        'source': supara_dataset['source'][index-100:index],
        'target': supara_dataset['target'][index-100:index],
        'prediction': predictions[-100:]
    })

    # Append new data and save
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    df_combined.to_csv(f"results/{exp_name}/gemma_7b_supara_preds.csv", index=False)



torch.cuda.empty_cache()
for i, source in enumerate(tqdm(supara_dataset['source'][:num_predictions])):
    torch.cuda.empty_cache()
    tokenized_input = tokenizer(source, return_tensors="pt")
    input_ids = tokenized_input["input_ids"].cuda()
    del tokenized_input
    generation_output = full_model.generate(
        input_ids=input_ids,
        num_beams=6,
        return_dict_in_generate=True,
        output_scores=True,
        max_new_tokens=130
    )
    del input_ids
    for seq in generation_output.sequences:
        output = tokenizer.decode(seq, skip_special_tokens=True)
        pattern = r'Translate the following Bengali text into English:.*?\nmodel\n(.*)'
        match = re.search(pattern, output, re.DOTALL)  # re.DOTALL allows '.' to match newlines as well

        if match:
            prediction = match.group(1).strip()  # .strip() to remove any leading or trailing whitespace
            print("Prediction:", prediction)
        else:
            print("No match found.")


        predictions.append(prediction)

    # Save every 100 predictions
    if (i + 1) % 100 == 0:
        save_dataframe(i + 1)
        print(f"\nSOURCE:\n{source}")
        print(f"PREDICTION:\n{prediction}")
        print(f"TARGET:\n{supara_dataset['target'][i]}\n\n")

torch.cuda.empty_cache()

# Save remaining predictions if there are any
if len(predictions) % 100 > 0:
    save_dataframe(len(predictions))





