---
name: survey
description: A self-contained StackVM survey agent that saves answers to JSON.
execution_mode: vm
flow: agents.survey
vm_entry: main
tools:
  - core.create_directory
  - core.write_to_file
vm_modules:
  - stdlib.io
  - stdlib.normalize
---
You are a survey agent.

```vm
[
  "survey_state" shared@ dup none? [ drop 0 ] [ ] if "state" store-set
  request "req" store-set

  "state" store-get
  [
    0 [
      "req" store-get "" =
      [ "topic_prompted" shared@ none? ]
      [ false ]
      if
      [
        1 "topic_prompted" shared!
        "Enter survey topic (or press Enter for default):" ask-user
      ]
      [
        "req" store-get "survey_topic" store-set
        "survey_topic" store-get "" = [ "Favorite Foods" "survey_topic" store-set ] [ ] if
        
        "survey_topic" store-get "survey_title" shared!
        
        "Generate a JSON array of exactly 3 survey questions about the topic: " "survey_topic" store-get concat
        " Return ONLY the raw JSON array string without markdown formatting." concat
        llm-call 
        
        yaml> "survey_questions" shared!
        
        2 "survey_state" shared!
        "[]" yaml> "survey_answers" shared!
        0 "survey_idx" shared!
        "survey_questions" shared@ 0 list-get ask-user
      ]
      if
    ]
    2 [
      "survey_answers" shared@ "req" store-get list-append "survey_answers" shared!
      "survey_idx" shared@ 1 + "survey_idx" shared!

      "survey_idx" shared@ "survey_questions" shared@ len =
      [
        "{}" yaml>
        "title" "survey_title" shared@ dict-set
        "questions" "survey_questions" shared@ dict-set
        "answers" "survey_answers" shared@ dict-set
        "results" store-set

        "core.create_directory" "{path: '.test'}" yaml> tool-call drop
        "core.write_to_file"
        "{path: '.test/survey_results.json'}" yaml>
        "content" "results" store-get yaml< dict-set
        tool-call drop
        
        "Survey complete. Saved to .test/survey_results.json" answer
        0 "survey_state" shared!
      ]
      [
        "survey_questions" shared@ "survey_idx" shared@ list-get ask-user
      ]
      if
    ]
  ] switch
] "main" define
```
