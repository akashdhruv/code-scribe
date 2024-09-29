# Prompt engineering for building diffusion stencils for constant and variable coefficient equation

# Import libraries
import re
import os, sys, toml, importlib, json

from typing import Optional
from alive_progress import alive_bar


class LlamaModel:
    def __init__(self, model):

        llama = importlib.import_module("llama")

        self.pipeline = llama.Llama.build(
            ckpt_dir=model,
            tokenizer_path=os.path.join(model, "tokenizer.model"),
            max_seq_len=4096,
            max_batch_size=8,
        )

        self.max_gen_len = None
        self.temperature = 0.5
        self.top_p = 0.95

    def chat(self, chat_template):
        results = self.pipeline.chat_completion(
            [chat_template],
            max_gen_len=self.max_gen_len,
            temperature=self.temperature,
            top_p=self.top_p,
        )
        print(results)
        return results[0]["generation"]["content"]


class OpenAIModel:
    def __init__(self):
        openai = importlib.import_module("openai")
        self.pipeline = openai.OpenAI()
        self.outputs = 1
        self.max_tokens = 4096

    def chat(self, chat_template):
        # We use the Chat Completion endpoint for chat like inputs
        response = self.pipeline.chat.completions.create(
            # model used here is ChatGPT
            # You can use all these models for this endpoint:
            # gpt-4, gpt-4-0314, gpt-4-32k, gpt-4-32k-0314,
            # gpt-3.5-turbo, gpt-3.5-turbo-0301
            # model="gpt-3.5-turbo",
            model="gpt-4o",
            messages=chat_template,
            # max_tokens generated by the AI model
            # maximu value can be 4096 tokens for "gpt-3.5-turbo"
            max_tokens=self.max_tokens,
            # number of output variations to be generated by AI model
            n=self.outputs,
        )

        return response.choices[0].message.content


class TFModel:
    def __init__(self, checkpoint_dir):
        transformers = importlib.import_module("transformers")
        torch = importlib.import_module("torch")

        self.tokenizer = transformers.AutoTokenizer.from_pretrained(checkpoint_dir)
        self.pipeline = transformers.pipeline(
            "text-generation",
            model=checkpoint_dir,
            # torch_dtype=torch.float16,
            device=-1,
        )

        self.max_new_tokens = 4096
        self.batch_size = 8
        self.max_length = None

    def chat(self, chat_template):

        results = self.pipeline(
            chat_template,
            max_new_tokens=self.max_new_tokens,
            max_length=self.max_length,
            batch_size=self.batch_size,
            # temperature=temperature,
            # top_p=top_p,
            # do_sample=True,
            eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=50256,
        )

        return results[0]["generated_text"][-1]["content"]


def prompt_translate(mapping, seed_prompt, model=None, save_prompts=False):
    """
    perform translation using prompts and the supplied model.
    """

    neural_model = None

    if model:
        print("Starting neural conversion process")

        if os.path.exists(model):
            neural_model = TFModel(model)

        elif model.lower() == "openai":
            neural_model = OpenAIModel()

        else:
            raise ValueError(f"{model} not available")

    if save_prompts:
        print("Saving custom prompts per file")

    chat_template = toml.load(seed_prompt)["chat"]

    with alive_bar(len(mapping[0]), bar="blocks") as bar:

        for fsource, csource, finterface, cdraft, promptfile in zip(
            mapping[0], mapping[1], mapping[2], mapping[3], mapping[4]
        ):

            bar.text(fsource)
            bar()

            if not os.path.isfile(csource) or save_prompts:
                cached_prompt = chat_template[-1]["content"]

                with open(fsource, "r") as sfile:
                    is_comment = False
                    source_code = []

                    for line in sfile.readlines():
                        is_comment = False

                        if line.strip().lower().startswith(("c", "!!", "!")) and (
                            not line.strip().lower().startswith(("complex"))
                        ):
                            is_comment = True

                        if not is_comment:
                            source_code.append(line)

                    if source_code:
                        chat_template[-1]["content"] += (
                            "\n" + "<source>\n" + "".join(source_code) + "</source>"
                        )

                if os.path.isfile(cdraft):

                    draft_code = []
                    with open(cdraft) as dfile:
                        for line in dfile.readlines():
                            draft_code.append(line)

                        if draft_code:
                            chat_template[-1]["content"] += (
                                "\n\n" + "<draft>\n" + "".join(draft_code) + "</draft>"
                            )

                if save_prompts:
                    with open(promptfile, "w") as pdest:
                        # for instance in chat_template:
                        #    pdest.write("[[chat]]\n")
                        #    pdest.write(f'role = "{instance["role"]}"\n')
                        #    pdest.write(f'content = """\n{instance["content"]}"""\n\n')
                        json.dump(chat_template, pdest, indent=4)
                    print(f"Generated prompt file for LLM consumption {promptfile}")

                if neural_model:
                    result = neural_model.chat(chat_template)

                    with open(csource, "w") as cdest, open(finterface, "w") as fdest:

                        csource = re.search(
                            r"<csource>(.*?)</csource>", result, re.DOTALL
                        )
                        fsource = re.search(
                            r"<fsource>(.*?)</fsource>", result, re.DOTALL
                        )

                        if csource:
                            cdest.write(csource.group(1))
                        else:
                            cdest.write(result)

                        if fsource:
                            fdest.write(fsource.group(1))

                chat_template[-1]["content"] = cached_prompt

            else:
                continue


def prompt_inspect(filelist, query_prompt, model=None, save_prompts=False):
    """
    Perform inspect on a list of files using a query prompt
    """
    neural_model = None

    if model:
        print("Performing neural inspection")

        if os.path.exists(model):
            neural_model = TFModel(model)

        elif model.lower() == "openai":
            neural_model = OpenAIModel()

        else:
            raise ValueError(f"{model} not available")

    if save_prompts:
        print("Saving prompts to scribe.json")

    chat_template = [{"role": "user", "content": ""}]

    chat_template[-1]["content"] += (
        "I will give you source code from a set of files that\n"
        + "belong to a scientific computing codebase. I want you\n"
        + "to understand the source code and answer a query that\n"
        + "follows. Source code for each will be separated using\n"
        + "elements <filename> ... </filename>. Additional\n"
        + "information related to the project structure may also be\n"
        + "provided within <index> ... </index>. This information will\n"
        + "contain an index of subroutines, functions, and modules contained\n"
        + "in each file. Note that you will find subroutines and functions\n"
        + "repeat along nodes in the directory tree. This maybe due to a directory-based\n"
        + "inheritance design implemented by the project. If the index element is not\n"
        + "present, then you may ignore it. The query prompt will be provided at then end\n"
        + "using elements <query> ... </query>.\n\n"
    )

    for fsource in filelist:
        with open(fsource, "r") as sfile:
            source_code = []

            for line in sfile.readlines():
                source_code.append(line)

        if source_code:
            chat_template[-1]["content"] += (
                "\n" + f"<{fsource}>\n" + "".join(source_code) + f"</{fsource}>\n"
            )

    chat_template[-1]["content"] += "\n" + f"<query>\n" + query_prompt + f"\n</query>\n"

    if save_prompts:
        with open("scribe.json", "w") as pdest:
            json.dump(chat_template, pdest, indent=4)

    if neural_model:
        result = neural_model.chat(chat_template)
        print(result)
