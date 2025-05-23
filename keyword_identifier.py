import openai
import os
from collections import defaultdict
import spacy

# Initialize OpenAI client
client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

def extract_image_prompts(story, num_prompts=5):
    nlp = spacy.load('en_core_web_sm')

    # Custom list of uninformative words
    uninformative_words = ['can', 'to', 'which', 'you', 'your', 'that','their','they']

    # Split the story into individual sentences
    doc = nlp(story)
    sentences = [sent.text.strip() for sent in doc.sents]

    # Find the main subject or noun phrase in each sentence
    main_subjects = []
    for sentence in sentences:
        doc = nlp(sentence.lower())
        for chunk in doc.noun_chunks:
            if chunk.root.dep_ == 'nsubj' and chunk.root.head.text.lower() != 'that':
                main_subjects.append(chunk)

    if main_subjects:
        main_subject = main_subjects[0]
    else:
        main_subject = None

    # Find the related words (adjectives, verbs) to the main subject
    related_words = defaultdict(list)
    for sentence in sentences:
        doc = nlp(sentence.lower())
        for tok in doc:
            # Avoid uninformative words and punctuation
            if tok.text in uninformative_words or not tok.text.isalnum():
                continue
            # If the token is a noun and it's not the main subject
            if (tok.pos_ == 'NOUN') and (main_subject is None or (tok.text != main_subject.text)):
                related_words[sentence].append(tok.text)

    # Create image prompts
    image_prompts = []
    for sentence, related in related_words.items():
        if main_subject is not None:
            prompt = f"{main_subject.text} {' '.join(related)} photorealistic"
        else:
            prompt = f"{sentence} photorealistic"
        image_prompts.append(prompt)

    # If we couldn't generate enough prompts, duplicate the existing ones
    if len(image_prompts) < num_prompts:
        print(f"Could only generate {len(image_prompts)} unique prompts out of the requested {num_prompts}. Duplicating prompts...")
        i = 0
        while len(image_prompts) < num_prompts:
            image_prompts.append(image_prompts[i])
            i = (i + 1) % len(image_prompts)  # cycle through existing prompts

    print("\nGenerated Image Prompts:")
    for idx, prompt in enumerate(image_prompts, start=1):
        print(f"{idx}: {prompt}")
    
    # Automatically proceed with generated prompts
    return image_prompts
