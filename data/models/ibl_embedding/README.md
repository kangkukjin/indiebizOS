---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- dense
- generated_from_trainer
- dataset_size:5335
- loss:MultipleNegativesRankingLoss
base_model: jhgan/ko-sroberta-multitask
widget:
- source_sentence: 화면 이 위치 눌러
  sentences:
  - '[self:mkdir]'
  - '[limbs:screen]'
  - 유튜브 동영상 조회·시청 (op 분기). 메타·자막·요약 + 시청 앱(추천 피드·시청 페이지·시청 기록 — 재생은 맥 경유 릴레이, 유튜브
    직접 접속 없음). 검색은 search_youtube.
- source_sentence: 내용을 3섹션 요약 보고서 구조로 정리
  sentences:
  - '[self:ledger]'
  - 원본 콘텐츠를 문서 IR 한 건(title·blocks 필드를 가진 단일 응답)으로 정리하는 편집자 원자 — 획득→구조화→렌더 파이프라인의
    중간. >> [table:document]로 이어 렌더.
  - 이 몸의 마이크로 음성 입력 (지표어·op 분기 — 폰=SpeechRecognizer/MediaRecorder, 데스크탑=ffmpeg 마이크+Gemini
    STT). 마이크 없는 몸이면 작동불능(정직 거절). 상시 청취 아닌 호출 시 1회.
- source_sentence: 날씨랑 소식 한번에
  sentences:
  - '[sense:weather] & [sense:search]'
  - '[self:music] >> [table:groupby] >> [table:chart]'
  - Gemini AI 이미지 생성·편집 (Nano Banana 2 기본). input_image에 원본 파일 경로를 주면 그 사진을 prompt
    지시대로 편집(인물 보정·배경 교체 등, 나머지 보존). style_preset으로 슬라이드 design_system과 일관된 일러스트. 옵션·모델은
    read_guide(query="Gemini 이미지").
- source_sentence: 두 리스트 이어붙여줘
  sentences:
  - '[sense:realty] & [sense:realty] >> [table:union]'
  - USB 손발 자격 원장 관리 (op 분기) — 발급·목록·폐기·승인. USB 에 담아 낯선 PC 에 꽂는 헬퍼의 인가는 허브 로그인 비밀번호가
    아니라 여기서 발급하는 limb key. 발급하면 USB 페이로드(헬퍼 설정+안내)를 만들어 경로를 돌려준다.
  - 파일 검색 — pattern(glob) 또는 메타(search_term 이름·extension·kind·min_size_mb, OS 색인 직접·선스캔
    불요·항상 최신). path로 검색 루트 지정(생략 시 glob=프로젝트, 메타=홈). 내용 검색은 grep.
- source_sentence: 폰 사진 10장 바탕화면에 저장해줘해
  sentences:
  - '[engines:image_gemini]'
  - '[engines:image_gemini] >> [limbs:os_open]'
  - '[self:photo] >> [self:copy]'
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
    '폰 사진 10장 바탕화면에 저장해줘해',
    '[self:photo] >> [self:copy]',
    '[engines:image_gemini]',
]
embeddings = model.encode(sentences)
print(embeddings.shape)
# [3, 768]

# Get the similarity scores for the embeddings
similarities = model.similarity(embeddings, embeddings)
print(similarities)
# tensor([[1.0000, 0.8289, 0.1028],
#         [0.8289, 1.0000, 0.1586],
#         [0.1028, 0.1586, 1.0000]])
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

* Size: 5,335 training samples
* Columns: <code>sentence_0</code> and <code>sentence_1</code>
* Approximate statistics based on the first 100 samples:
  |          | sentence_0                                                                       | sentence_1                                                                        |
  |:---------|:---------------------------------------------------------------------------------|:----------------------------------------------------------------------------------|
  | type     | string                                                                           | string                                                                            |
  | modality | text                                                                             | text                                                                              |
  | details  | <ul><li>min: 5 tokens</li><li>mean: 16.2 tokens</li><li>max: 64 tokens</li></ul> | <ul><li>min: 7 tokens</li><li>mean: 23.19 tokens</li><li>max: 64 tokens</li></ul> |
* Samples:
  | sentence_0                                                                                                                                   | sentence_1                                                                                                                                                                                                      |
  |:---------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
  | <code>텍스트의 철학적 주제나 상징적 비유를 시각화하여 미니멀한 흑백 라인 아트 삽화 만들어</code>                                                                                 | <code>Gemini AI 이미지 생성·편집 (Nano Banana 2 기본). input_image에 원본 파일 경로를 주면 그 사진을 prompt 지시대로 편집(인물 보정·배경 교체 등, 나머지 보존). style_preset으로 슬라이드 design_system과 일관된 일러스트. 옵션·모델은 read_guide(query="Gemini 이미지").</code> |
  | <code>안드로이드 폰 화면 조작 (op 분기) — snapshot으로 요소 읽고 ref/좌표로 탭. 집 PC=USB-ADB 연결 폰, 폰 자신=네이티브 접근성(자급). 데스크톱은 limbs:screen, 웹은 limbs:browser.</code> | <code>[limbs:android]</code>                                                                                                                                                                                    |
  | <code>날씨 볼 수 있어?</code>                                                                                                                      | <code>[self:discover]</code>                                                                                                                                                                                    |
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
| 0.7496 | 500  | 0.0177        |


### Training Time
- **Training**: 3.5 minutes

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