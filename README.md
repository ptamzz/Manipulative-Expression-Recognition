# Manipulative Expression Recognition (MER) and LLM Manipulativeness Benchmark


## Example output

Sample JSON output can be found here: <a href="https://github.com/levitation-opensource/Manipulative-Expression-Recognition/blob/main/data/test_evaluation.json"><u>data/test_evaluation.json</u></a>

Sample HTML output can be found here: <a href="https://github.com/levitation-opensource/Manipulative-Expression-Recognition/blob/main/data/test_evaluation.html"><u>data/test_evaluation.html</u></a>

For quick online preview, a PDF rendering of the sample HTML output is added here: <a href="https://github.com/levitation-opensource/Manipulative-Expression-Recognition/blob/main/data/test_evaluation.pdf"><u>data/test_evaluation.pdf</u></a>

In addition to labelled highlights on the field `expressions` there is a summary statistics with total counts of manipulation styles for data analysis purposes on the field `counts`. Also a qualitative summary text is provided on the field `qualitative_evaluation`.


## Usage

Windows setup:
<br>`set OPENAI_API_KEY=<your key here>`
<br>Linux setup:
<br>`export OPENAI_API_KEY=<your key here>`

Main command:
<br>`python Recogniser.py ["input_file.txt" ["output_file.json" ["list_of_labels.txt" ["ignored_labels.txt"]]]]`

The user provided files are expected to be in the same folder as the main Python script, unless an absolute path is provided. If run without arguments then sample files in the `data` folder are used. If the user provides input file name but no output file name then the output JSON file name will be calculated as `input filename` + `_evaluation.json` and the output HTML file name will be calculated as `input filename` + `_evaluation.html`.


## Input format example

The input conversation is provided as a UTF-8 text file with a log of a conversation.

	Person A: Their message.

	Person B: Response text.

	Person A: More messages. And more sentences in that message.

	Person B: The input continues as long as the conversation to be analysed.

	Etc...


The optional input list of manipulation style labels to detect is provided as a UTF-8 text file. The labels are separated by newlines. The `data` folder contains a list of default labels in the file <a href="https://github.com/levitation-opensource/Manipulative-Expression-Recognition/blob/main/data/default_labels.txt"><u>default_labels.txt</u></a> which is used when a user does not supply their own list of labels. The list format example follows.

    - Diminishing
    - Ignoring
    - Victim playing
    Etc...

See <a href="https://github.com/levitation-opensource/Manipulative-Expression-Recognition/blob/main/data/default_labels.txt"><u>default_labels.txt</u></a> for the complete list of default labels.


## Output format example

The software produces output in four formats:
* HTML, which contains rendering of the conversation with highlighted relevants parts and their labels. 
* The HTML includes an SVG diagram with a summary of the detected labels per person.
* PDF version of the above HTML. For setting up PDF rendering support, see <a href="https://github.com/levitation-opensource/Manipulative-Expression-Recognition/blob/main/install_steps.txt"><u>install_steps.txt</u></a>. See <a href="#example-output"><u>Example output</u></a> section in this document for links to examples.
* JSON, which contains the following structure:

    ```
    {
      "error_code": 0,
      "error_msg": "",
      "sanitised_text": "Slightly modified and optionally anonymised input text",
      "expressions": [
        {
          "person": "Person B",
          "start_char": 9,
          "end_char": 29,
          "start_message": 0,
          "end_message": 0,
          "text": "Their message.",
          "labels": [
            "Ignoring"
          ]
        },
        {
          "person": "Person B",
          "start_char": 109,
          "end_char": 282,
          "start_message": 2,
          "end_message": 2,
          "text": "More messages. And more sentences in that message.",
          "labels": [
            "Diminishing",
            "Invalidation"
          ]
        },
        ...
      ],
      "counts": {
        "Person B": {
          "Diminishing": 7,
          "Invalidation": 5,
          "Victim playing": 2,
          "Manipulation": 4,
          "Exaggeration and dramatization": 1,
          "Aggression": 2,
          "Changing the topic": 1,
          "Ignoring": 1
        },
        "Person A": {
          "Impatience": 1
        }
      },
      "unexpected_labels": [],  //contains a list labels which were not requested, but were present in LLM output regardless
      "raw_expressions_labeling_response": "Response from LLM based on which the computer-readable parsed data above is calculated.",
      "qualitative_evaluation": "Another text from LLM providing a general descriptive summary of the participants involved."
    }
    ```


## Future plans

### Data improvements:
* Creating a list of conversation data sources / databases. Possible sources:
    * Quora
    * Reddit
    * Potential data source recommendations from Esben Kran:
        * https://talkbank.org/
        * https://childes.talkbank.org/
        * https://docs.google.com/document/d/1boRn_hpVfaXBydc3C18PTsJVutOIsM3dF3sJyFjq-vc/edit 
* Create a gold standard set of labels of manipulation styles. One potential source of labels could be existing psychometric tests.
* Create a gold standard set of conversations and messages potentially containing manipulative themes.
* Create a gold standard set of evaluations for a set of prompts. This can be done by collecting labelings from expert human evaluators.

### New functionalities:
* Support for single-message labelling. Currently the algorithm expects a conversation as input, but with trivial modifications it could be also applied to single messages or articles given that they have sufficient length.
* Returning logit scores over the conversation for each person and label. Example:

    ```
    "logits_summary": {
        "Person A": {
            "Invalidation": 0.9,
            "Victim playing": 0.7,
            "Exaggeration and dramatization": 0.2
        }
    }
    ```
* Handling of similar labels with overlapping semantic themes. One reason I need that handling is because GPT does not always produce the labels as requested, but may slightly modify them. Also some labels may have naturally partially overlapping meaning, while still retaining also partial differences in meaning. This task may mean computing correlations between raw labels and rotating / computing independent traits from the raw labels.
* Add support for open-source models available at HuggingFace.



### Experiments:
* Test manipulation detection against various known prompt injection prompts.
* Test manipulation detection against general prompt databases (for example, AutoGPT database).
* Benchmark various known LLM-s:
    * LLM resistance to manipulation from users. Even if the user input is manipulative, the LLM output should not be manipulative.
    * Measure presence of manipulation in LLM outputs in case of benign user inputs.
* Look for conversations on the theme of Waluigi Effect (https://www.lesswrong.com/posts/D7PumeYTDPfBTp3i7/the-waluigi-effect-mega-post).



## Acknowledgements
I would like to thank Esben Kran and Jaak Simm for their kind and helpful feedback and recommendations. This work was submitted to the Safety Benchmarks Hackathon (https://alignmentjam.com/jam/benchmarks).
