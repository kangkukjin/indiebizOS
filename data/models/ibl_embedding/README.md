---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- dense
- generated_from_trainer
- dataset_size:4099
- loss:MultipleNegativesRankingLoss
base_model: jhgan/ko-sroberta-multitask
widget:
- source_sentence: record audio for 10 seconds
  sentences:
  - '[self:trigger]'
  - 폰 마이크로 음성 입력 (op 분기). 상시 청취 아닌 호출 시 1회. transcribe=받아쓰기(STT→텍스트), record=녹음(→파일).
  - '[self:edit]'
- source_sentence: 브라우저 네트워크 트래픽 보여줘
  sentences:
  - '[limbs:browser]'
  - 'Shadcn UI HTML 슬라이드(2층: 글자 레이어 + 별도 그림 합성). **마케팅·랜딩·피치덱·순수 텍스트 레이아웃 덱 전용.**
    ★강의·발표·NotebookLM식 슬라이드는 이 액션을 쓰지 말 것 — 대신 [engines:slide]{style:"native"}(슬라이드마다
    통짜 이미지) 또는 [self:lecture] 워크스페이스(design_system 미지정=native 기본)를 써라(시각=의미 융합·한글
    OCR 검증). 슬라이드 IR(slides[]) → png/pdf/pptx emit.'
  - '[others:auto_response]'
- source_sentence: HTML 돌려줘 결과 봐
  sentences:
  - '[limbs:browser]'
  - 주식 시세·거래 데이터 조회 (op 분기). 기업 펀더멘털은 company, 암호화폐는 crypto.
  - HTML 페이지를 PNG 이미지로 렌더링. 슬라이드·차트 결과를 이미지화.
- source_sentence: 특정 웹 리소스를 참조하여 핵심 개념을 시각적 대비 구조로 요약한 강의 슬라이드 만들어 및 즉시 확인
  sentences:
  - '[self:photo]'
  - 웹페이지 원문 읽기 (URL 필요). items=문서 IR(type+text 항목). 검색 스니펫으로 부족할 때 상세 내용 확인용.
  - '[self:health]'
- source_sentence: 전체 기록해줘소 요약 좀
  sentences:
  - 디스크 용량 분석 (op 분기) — 폴더·확장자별 용량 집계. scan(분석 인덱스 구축)/summary(용량 집계)/volumes(볼륨 목록).
    ★파일 검색은 fs_query·디스크 여유공간은 sense:host (둘 다 스캔 불요).
  - 슬라이드 한 장 관리 (op 분기). 생성/편집/삭제/필드 패치/재렌더.
  - '[limbs:radio_favorite]'
pipeline_tag: sentence-similarity
library_name: sentence-transformers
---

# SentenceTransformer based on jhgan/ko-sroberta-multitask

This is a [sentence-transformers](https://www.SBERT.net) model finetuned from [jhgan/ko-sroberta-multitask](https://huggingface.co/jhgan/ko-sroberta-multitask). It maps sentences & paragraphs to a 768-dimensional dense vector space and can be used for semantic textual similarity, semantic search, paraphrase mining, text classification, clustering, and more.

## Model Details

### Model Description
- **Model Type:** Sentence Transformer
- **Base model:** [jhgan/ko-sroberta-multitask](https://huggingface.co/jhgan/ko-sroberta-multitask) <!-- at revision 8fca7c9c98c26599be0e14b9916b11a756a26f19 -->
- **Maximum Sequence Length:** 64 tokens
- **Output Dimensionality:** 768 dimensions
- **Similarity Function:** Cosine Similarity
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
  (0): Transformer({'max_seq_length': 64, 'do_lower_case': False, 'architecture': 'RobertaModel'})
  (1): Pooling({'word_embedding_dimension': 768, 'pooling_mode_cls_token': False, 'pooling_mode_mean_tokens': True, 'pooling_mode_max_tokens': False, 'pooling_mode_mean_sqrt_len_tokens': False, 'pooling_mode_weightedmean_tokens': False, 'pooling_mode_lasttoken': False, 'include_prompt': True})
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
    '전체 기록해줘소 요약 좀',
    '디스크 용량 분석 (op 분기) — 폴더·확장자별 용량 집계. scan(분석 인덱스 구축)/summary(용량 집계)/volumes(볼륨 목록). ★파일 검색은 fs_query·디스크 여유공간은 sense:host (둘 다 스캔 불요).',
    '[limbs:radio_favorite]',
]
embeddings = model.encode(sentences)
print(embeddings.shape)
# [3, 768]

# Get the similarity scores for the embeddings
similarities = model.similarity(embeddings, embeddings)
print(similarities)
# tensor([[ 1.0000,  0.6602, -0.1586],
#         [ 0.6602,  1.0000, -0.1120],
#         [-0.1586, -0.1120,  1.0000]])
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

* Size: 4,099 training samples
* Columns: <code>sentence_0</code> and <code>sentence_1</code>
* Approximate statistics based on the first 1000 samples:
  |         | sentence_0                                                                        | sentence_1                                                                       |
  |:--------|:----------------------------------------------------------------------------------|:---------------------------------------------------------------------------------|
  | type    | string                                                                            | string                                                                           |
  | details | <ul><li>min: 4 tokens</li><li>mean: 13.07 tokens</li><li>max: 64 tokens</li></ul> | <ul><li>min: 7 tokens</li><li>mean: 21.3 tokens</li><li>max: 64 tokens</li></ul> |
* Samples:
  | sentence_0                       | sentence_1                                                                          |
  |:---------------------------------|:------------------------------------------------------------------------------------|
  | <code>인공지능 뉴스 최근 거</code>        | <code>[sense:search_news]</code>                                                    |
  | <code>외장하드 포식하면서 알아낸 거 보여</code> | <code>포식 기억(냄새지도) — 과거 디스크·코드·웹 포식에서 배운 폴더/모듈 정체·관습·죽은가지·주인모델을 누적·회상. op 분기.</code> |
  | <code>비트코인 투자할만해?</code>         | <code>암호화폐 시세 (CoinGecko: BTC, ETH, XRP 등 USD/KRW)</code>                           |
* Loss: [<code>MultipleNegativesRankingLoss</code>](https://sbert.net/docs/package_reference/sentence_transformer/losses.html#multiplenegativesrankingloss) with these parameters:
  ```json
  {
      "scale": 20.0,
      "similarity_fct": "cos_sim",
      "gather_across_devices": false
  }
  ```

### Training Hyperparameters
#### Non-Default Hyperparameters

- `num_train_epochs`: 1
- `multi_dataset_batch_sampler`: round_robin

#### All Hyperparameters
<details><summary>Click to expand</summary>

- `do_predict`: False
- `eval_strategy`: no
- `prediction_loss_only`: True
- `per_device_train_batch_size`: 8
- `per_device_eval_batch_size`: 8
- `gradient_accumulation_steps`: 1
- `eval_accumulation_steps`: None
- `torch_empty_cache_steps`: None
- `learning_rate`: 5e-05
- `weight_decay`: 0.0
- `adam_beta1`: 0.9
- `adam_beta2`: 0.999
- `adam_epsilon`: 1e-08
- `max_grad_norm`: 1
- `num_train_epochs`: 1
- `max_steps`: -1
- `lr_scheduler_type`: linear
- `lr_scheduler_kwargs`: None
- `warmup_ratio`: None
- `warmup_steps`: 0
- `log_level`: passive
- `log_level_replica`: warning
- `log_on_each_node`: True
- `logging_nan_inf_filter`: True
- `enable_jit_checkpoint`: False
- `save_on_each_node`: False
- `save_only_model`: False
- `restore_callback_states_from_checkpoint`: False
- `use_cpu`: False
- `seed`: 42
- `data_seed`: None
- `bf16`: False
- `fp16`: False
- `bf16_full_eval`: False
- `fp16_full_eval`: False
- `tf32`: None
- `local_rank`: -1
- `ddp_backend`: None
- `debug`: []
- `dataloader_drop_last`: False
- `dataloader_num_workers`: 0
- `dataloader_prefetch_factor`: None
- `disable_tqdm`: False
- `remove_unused_columns`: True
- `label_names`: None
- `load_best_model_at_end`: False
- `ignore_data_skip`: False
- `fsdp`: []
- `fsdp_config`: {'min_num_params': 0, 'xla': False, 'xla_fsdp_v2': False, 'xla_fsdp_grad_ckpt': False}
- `accelerator_config`: {'split_batches': False, 'dispatch_batches': None, 'even_batches': True, 'use_seedable_sampler': True, 'non_blocking': False, 'gradient_accumulation_kwargs': None}
- `parallelism_config`: None
- `deepspeed`: None
- `label_smoothing_factor`: 0.0
- `optim`: adamw_torch_fused
- `optim_args`: None
- `group_by_length`: False
- `length_column_name`: length
- `project`: huggingface
- `trackio_space_id`: trackio
- `ddp_find_unused_parameters`: None
- `ddp_bucket_cap_mb`: None
- `ddp_broadcast_buffers`: False
- `dataloader_pin_memory`: True
- `dataloader_persistent_workers`: False
- `skip_memory_metrics`: True
- `push_to_hub`: False
- `resume_from_checkpoint`: None
- `hub_model_id`: None
- `hub_strategy`: every_save
- `hub_private_repo`: None
- `hub_always_push`: False
- `hub_revision`: None
- `gradient_checkpointing`: False
- `gradient_checkpointing_kwargs`: None
- `include_for_metrics`: []
- `eval_do_concat_batches`: True
- `auto_find_batch_size`: False
- `full_determinism`: False
- `ddp_timeout`: 1800
- `torch_compile`: False
- `torch_compile_backend`: None
- `torch_compile_mode`: None
- `include_num_input_tokens_seen`: no
- `neftune_noise_alpha`: None
- `optim_target_modules`: None
- `batch_eval_metrics`: False
- `eval_on_start`: False
- `use_liger_kernel`: False
- `liger_kernel_config`: None
- `eval_use_gather_object`: False
- `average_tokens_across_devices`: True
- `use_cache`: False
- `prompts`: None
- `batch_sampler`: batch_sampler
- `multi_dataset_batch_sampler`: round_robin
- `router_mapping`: {}
- `learning_rate_mapping`: {}

</details>

### Training Logs
| Epoch  | Step | Training Loss |
|:------:|:----:|:-------------:|
| 0.9747 | 500  | 0.0163        |


### Framework Versions
- Python: 3.14.5
- Sentence Transformers: 5.2.2
- Transformers: 5.1.0
- PyTorch: 2.10.0
- Accelerate: 1.13.0
- Datasets: 4.8.4
- Tokenizers: 0.22.2

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
@misc{henderson2017efficient,
    title={Efficient Natural Language Response Suggestion for Smart Reply},
    author={Matthew Henderson and Rami Al-Rfou and Brian Strope and Yun-hsuan Sung and Laszlo Lukacs and Ruiqi Guo and Sanjiv Kumar and Balint Miklos and Ray Kurzweil},
    year={2017},
    eprint={1705.00652},
    archivePrefix={arXiv},
    primaryClass={cs.CL}
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