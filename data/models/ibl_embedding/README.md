---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- dense
- generated_from_trainer
- dataset_size:6470
- loss:MultipleNegativesRankingLoss
base_model: jhgan/ko-sroberta-multitask
widget:
- source_sentence: 목표 상태 체크
  sentences:
  - 목표 프로세스 관리 (op 분기). list/status/kill/delete/log/attempts. 의식 에이전트가 평가 루프 라운드를
    누적·종료하는 메타 인지 도구.
  - '[self:time] & [sense:stock]'
  - '[self:delete] ; [self:file_find] >> [table:take] >> [table:document]'
- source_sentence: 매일 아침 9시에 뉴스 모아서 메일로 보내는 걸 예약해줘
  sentences:
  - '[self:trigger] >> [table:take] >> [others:channel_send]"}'
  - 웹·뉴스 통합 검색 — source 로 엔진 선택. ddg(기본, 글로벌 웹)/naver(한국어 콘텐츠 — 한국어 질의는 이쪽)/gnews(구글
    뉴스)/hn(Hacker News 기술)/guardian(가디언 아카이브, 영어). 유튜브·논문·지역·쇼핑은 각 도메인 검색 액션.
  - '[engines:image_gemini]", style_preset: "", aspect_ratio: "", image_size: "",
    output_path: ""} >> [engines:image_read]", intent: ""} >> [engines:image_read]",
    prompt: ""} & [self:copy]", dest: ""}'
- source_sentence: 블로그 새 글 받아오고 최신글 창고에 발행해줘
  sentences:
  - '[sense:stock] & [sense:stock] & [sense:stock] & [sense:search]'
  - '[self:deck]'
  - '[self:blog] ; [self:blog] >> [self:read] >> [table:document] >> [self:copy]'
- source_sentence: 오른쪽 클릭 — table_row_3
  sentences:
  - '[limbs:browser]'
  - '[self:grep] & [self:list] & [self:file_find] & [self:read] & [self:read]'
  - Gemini Vision 이미지 읽기·평가 (op 분기). read(기본)=시각 QA·OCR·자유서술 답변, critic=의도 정합 채점(passed/score/issues/notes).
- source_sentence: '사용자가 특정 식당을 언급하며 다른 대안을 요청하는 상황에서, 가족 구성원의 기호(예: 조개 불호)를 고려해 대안
    식당을 탐색·비교·추천한다'
  sentences:
  - '[self:write]'
  - '[sense:realty] >> [table:take] >> [table:brief]'
  - '[sense:restaurant]'
pipeline_tag: sentence-similarity
library_name: sentence-transformers
---

# SentenceTransformer based on jhgan/ko-sroberta-multitask

This is a [sentence-transformers](https://www.SBERT.net) model finetuned from [jhgan/ko-sroberta-multitask](https://huggingface.co/jhgan/ko-sroberta-multitask). It maps sentences & paragraphs to a 768-dimensional dense vector space and can be used for semantic textual similarity, semantic search, paraphrase mining, classification, clustering, and more.

## Model Details

### Model Description
- **Model Type:** Sentence Transformer
- **Base model:** [jhgan/ko-sroberta-multitask](https://huggingface.co/jhgan/ko-sroberta-multitask) <!-- at revision 8fca7c9c98c26599be0e14b9916b11a756a26f19 -->
- **Maximum Sequence Length:** 64 tokens
- **Output Dimensionality:** 768 dimensions
- **Similarity Function:** Cosine Similarity
- **Supported Modality:** Text
<!-- - **Training Dataset:** Unknown -->
<!-- - **Language:** Unknown -->
<!-- - **License:** Unknown -->

### Model Sources

- **Documentation:** [Sentence Transformers Documentation](https://sbert.net)
- **Repository:** [Sentence Transformers on GitHub](https://github.com/huggingface/sentence-transformers)
- **Hugging Face:** [Sentence Transformers on Hugging Face](https://huggingface.co/models?library=sentence-transformers)

### Full Model Architecture

```
SentenceTransformer(
  (0): Transformer({'transformer_task': 'feature-extraction', 'modality_config': {'text': {'method': 'forward', 'method_output_name': 'last_hidden_state'}}, 'module_output_name': 'token_embeddings', 'architecture': 'RobertaModel'})
  (1): Pooling({'embedding_dimension': 768, 'pooling_mode': 'mean', 'include_prompt': True})
)
```

## Usage

### Direct Usage (Sentence Transformers)

First install the Sentence Transformers library:

```bash
pip install -U sentence-transformers
```
Then you can load this model and run inference.
```python
from sentence_transformers import SentenceTransformer

# Download from the 🤗 Hub
model = SentenceTransformer("sentence_transformers_model_id")
# Run inference
sentences = [
    '사용자가 특정 식당을 언급하며 다른 대안을 요청하는 상황에서, 가족 구성원의 기호(예: 조개 불호)를 고려해 대안 식당을 탐색·비교·추천한다',
    '[sense:restaurant]',
    '[sense:realty] >> [table:take] >> [table:brief]',
]
embeddings = model.encode(sentences)
print(embeddings.shape)
# [3, 768]

# Get the similarity scores for the embeddings
similarities = model.similarity(embeddings, embeddings)
print(similarities)
# tensor([[ 1.0000,  0.5861,  0.0365],
#         [ 0.5861,  1.0000, -0.1440],
#         [ 0.0365, -0.1440,  1.0000]])
```
<!--
### Direct Usage (Transformers)

<details><summary>Click to see the direct usage in Transformers</summary>

</details>
-->

<!--
### Downstream Usage (Sentence Transformers)

You can finetune this model on your own dataset.

<details><summary>Click to expand</summary>

</details>
-->

<!--
### Out-of-Scope Use

*List how the model may foreseeably be misused and address what users ought not to do with the model.*
-->

<!--
## Bias, Risks and Limitations

*What are the known or foreseeable issues stemming from this model? You could also flag here known failure cases or weaknesses of the model.*
-->

<!--
### Recommendations

*What are recommendations with respect to the foreseeable issues? For example, filtering explicit content.*
-->

## Training Details

### Training Dataset

#### Unnamed Dataset

* Size: 6,470 training samples
* Columns: <code>sentence_0</code> and <code>sentence_1</code>
* Approximate statistics based on the first 100 samples:
  |          | sentence_0                                                                        | sentence_1                                                                        |
  |:---------|:----------------------------------------------------------------------------------|:----------------------------------------------------------------------------------|
  | type     | string                                                                            | string                                                                            |
  | modality | text                                                                              | text                                                                              |
  | details  | <ul><li>min: 4 tokens</li><li>mean: 15.41 tokens</li><li>max: 64 tokens</li></ul> | <ul><li>min: 7 tokens</li><li>mean: 25.83 tokens</li><li>max: 64 tokens</li></ul> |
* Samples:
  | sentence_0                           | sentence_1                                                                                      |
  |:-------------------------------------|:------------------------------------------------------------------------------------------------|
  | <code>강의 동영상 렌더 다 됐는지 봐줘해줘</code>    | <code>[self:deck]</code>                                                                        |
  | <code>새로운 테스트 시작해줘</code>            | <code>주식 시세·거래 데이터 조회 (op 분기). 기업 펀더멘털은 company, 암호화폐는 crypto.</code>                           |
  | <code>뉴스수집-요약-저장 워크플로우 새로 만들어</code> | <code>[self:workflow], do: "[sense:search]'} >> [table:brief] >> [self:write]_리포트.md'}"}</code> |
* Loss: [<code>MultipleNegativesRankingLoss</code>](https://sbert.net/docs/package_reference/sentence_transformer/losses.html#multiplenegativesrankingloss) with these parameters:
  ```json
  {
      "scale": 20.0,
      "similarity_fct": "cos_sim",
      "gather_across_devices": false,
      "directions": [
          "query_to_doc"
      ],
      "partition_mode": "joint",
      "hardness_mode": null,
      "hardness_strength": 0.0
  }
  ```

### Training Hyperparameters
#### Non-Default Hyperparameters

- `num_train_epochs`: 1
- `multi_dataset_batch_sampler`: round_robin

#### All Hyperparameters
<details><summary>Click to expand</summary>

- `per_device_train_batch_size`: 8
- `num_train_epochs`: 1
- `max_steps`: -1
- `learning_rate`: 5e-05
- `lr_scheduler_type`: linear
- `lr_scheduler_kwargs`: None
- `warmup_steps`: 0
- `optim`: adamw_torch_fused
- `optim_args`: None
- `weight_decay`: 0.0
- `adam_beta1`: 0.9
- `adam_beta2`: 0.999
- `adam_epsilon`: 1e-08
- `optim_target_modules`: None
- `gradient_accumulation_steps`: 1
- `average_tokens_across_devices`: True
- `max_grad_norm`: 1
- `label_smoothing_factor`: 0.0
- `bf16`: False
- `fp16`: False
- `bf16_full_eval`: False
- `fp16_full_eval`: False
- `tf32`: None
- `gradient_checkpointing`: False
- `gradient_checkpointing_kwargs`: None
- `torch_compile`: False
- `torch_compile_backend`: None
- `torch_compile_mode`: None
- `use_liger_kernel`: False
- `liger_kernel_config`: None
- `use_cache`: False
- `neftune_noise_alpha`: None
- `torch_empty_cache_steps`: None
- `auto_find_batch_size`: False
- `log_on_each_node`: True
- `logging_nan_inf_filter`: True
- `include_num_input_tokens_seen`: no
- `log_level`: passive
- `log_level_replica`: warning
- `disable_tqdm`: False
- `project`: huggingface
- `trackio_space_id`: None
- `trackio_bucket_id`: None
- `trackio_static_space_id`: None
- `per_device_eval_batch_size`: 8
- `prediction_loss_only`: True
- `eval_on_start`: False
- `eval_do_concat_batches`: True
- `eval_use_gather_object`: False
- `eval_accumulation_steps`: None
- `include_for_metrics`: []
- `batch_eval_metrics`: False
- `save_only_model`: False
- `save_on_each_node`: False
- `enable_jit_checkpoint`: False
- `push_to_hub`: False
- `hub_private_repo`: None
- `hub_model_id`: None
- `hub_strategy`: every_save
- `hub_always_push`: False
- `hub_revision`: None
- `load_best_model_at_end`: False
- `ignore_data_skip`: False
- `restore_callback_states_from_checkpoint`: False
- `full_determinism`: False
- `seed`: 42
- `data_seed`: None
- `use_cpu`: False
- `accelerator_config`: {'split_batches': False, 'dispatch_batches': None, 'even_batches': True, 'use_seedable_sampler': True, 'non_blocking': False, 'gradient_accumulation_kwargs': None}
- `parallelism_config`: None
- `dataloader_drop_last`: False
- `dataloader_num_workers`: 0
- `dataloader_pin_memory`: True
- `dataloader_persistent_workers`: False
- `dataloader_prefetch_factor`: None
- `remove_unused_columns`: True
- `label_names`: None
- `train_sampling_strategy`: random
- `length_column_name`: length
- `ddp_find_unused_parameters`: None
- `ddp_bucket_cap_mb`: None
- `ddp_broadcast_buffers`: False
- `ddp_static_graph`: None
- `ddp_backend`: None
- `ddp_timeout`: 1800
- `fsdp`: None
- `fsdp_config`: None
- `deepspeed`: None
- `debug`: []
- `skip_memory_metrics`: True
- `do_predict`: False
- `resume_from_checkpoint`: None
- `warmup_ratio`: None
- `local_rank`: -1
- `prompts`: None
- `batch_sampler`: batch_sampler
- `multi_dataset_batch_sampler`: round_robin
- `router_mapping`: {}
- `learning_rate_mapping`: {}

</details>

### Training Logs
| Epoch  | Step | Training Loss |
|:------:|:----:|:-------------:|
| 0.6180 | 500  | 0.0177        |


### Training Time
- **Training**: 4.4 minutes

### Framework Versions
- Python: 3.13.5
- Sentence Transformers: 5.7.0
- Transformers: 5.14.1
- PyTorch: 2.13.0
- Accelerate: 1.14.0
- Datasets: 5.0.1
- Tokenizers: 0.22.2

## Additional Resources

- [Training and Finetuning Embedding Models with Sentence Transformers](https://huggingface.co/blog/train-sentence-transformers): the end-to-end guide for training or finetuning Sentence Transformer models.
- [Introduction to Matryoshka Embedding Models](https://huggingface.co/blog/matryoshka): variable-size embeddings that can be truncated with minimal quality loss.
- [Binary and Scalar Embedding Quantization for Significantly Faster & Cheaper Retrieval](https://huggingface.co/blog/embedding-quantization): post-training compression of embedding vectors.
- [Multimodal Embedding & Reranker Models with Sentence Transformers](https://huggingface.co/blog/multimodal-sentence-transformers): use text, image, audio, and video models through the same API.
- [Training and Finetuning Multimodal Embedding & Reranker Models with Sentence Transformers](https://huggingface.co/blog/train-multimodal-sentence-transformers): train multimodal embedding models, with a Visual Document Retrieval walkthrough.

## Citation

### BibTeX

#### Sentence Transformers
```bibtex
@inproceedings{reimers-2019-sentence-bert,
    title = "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks",
    author = "Reimers, Nils and Gurevych, Iryna",
    booktitle = "Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing",
    month = "11",
    year = "2019",
    publisher = "Association for Computational Linguistics",
    url = "https://arxiv.org/abs/1908.10084",
}
```

#### MultipleNegativesRankingLoss
```bibtex
@misc{oord2019representationlearningcontrastivepredictive,
      title={Representation Learning with Contrastive Predictive Coding},
      author={Aaron van den Oord and Yazhe Li and Oriol Vinyals},
      year={2019},
      eprint={1807.03748},
      archivePrefix={arXiv},
      primaryClass={cs.LG},
      url={https://arxiv.org/abs/1807.03748},
}
```

<!--
## Glossary

*Clearly define terms in order to be accessible across audiences.*
-->

<!--
## Model Card Authors

*Lists the people who create the model card, providing recognition and accountability for the detailed work that goes into its construction.*
-->

<!--
## Model Card Contact

*Provides a way for people who have updates to the Model Card, suggestions, or questions, to contact the Model Card authors.*
-->