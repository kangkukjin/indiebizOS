---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- dense
- generated_from_trainer
- dataset_size:14446
- loss:MultipleNegativesRankingLoss
base_model: jhgan/ko-sroberta-multitask
widget:
- source_sentence: 사진 정리하는 기능 있어?
  sentences:
  - 날씨 어떻게 확인해
  - 공연 장르 코드 목록 조회
  - 쓸데없는 파일 삭제
- source_sentence: Pew Research 여론조사 데이터
  sentences:
  - 볼륨 뭐가 있어 보여줘
  - 파이썬 스크립트 어디있어
  - Pew Research 최신 여론조사/리서치 보고서 목록. 미국 사회·정치·기술 트렌드 조사. 파라미터 없이 호출하면 최신 리서치 목록 반환.
- source_sentence: 연락처 전체 목록 보여줘
  sentences:
  - '[self:health_query]'
  - 수집 데이터 남겨줘해줘
  - 연락처 전체 뭐가 있어
- source_sentence: 집 설계 리스트 보여줄래
  sentences:
  - '[self:search_memory]'
  - '[engines:arch_list]'
  - PubMed 논문 내려받아
- source_sentence: 사진 타임라인 보여줘
  sentences:
  - 사진 타임라인 보여
  - 즐겨찾기 라디오 보여
  - 주식 볼 수 있는 기능 있나
pipeline_tag: sentence-similarity
library_name: sentence-transformers
---

# SentenceTransformer based on jhgan/ko-sroberta-multitask

This is a [sentence-transformers](https://www.SBERT.net) model finetuned from [jhgan/ko-sroberta-multitask](https://huggingface.co/jhgan/ko-sroberta-multitask). It maps sentences & paragraphs to a 768-dimensional dense vector space and can be used for semantic textual similarity, semantic search, paraphrase mining, text classification, clustering, and more.

## Model Details

### Model Description
- **Model Type:** Sentence Transformer
- **Base model:** [jhgan/ko-sroberta-multitask](https://huggingface.co/jhgan/ko-sroberta-multitask) <!-- at revision ab957ae6a91e99c4cad36d52063a2a9cf1bf4419 -->
- **Maximum Sequence Length:** 128 tokens
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
  (0): Transformer({'max_seq_length': 128, 'do_lower_case': False, 'architecture': 'RobertaModel'})
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
    '사진 타임라인 보여줘',
    '사진 타임라인 보여',
    '즐겨찾기 라디오 보여',
]
embeddings = model.encode(sentences)
print(embeddings.shape)
# [3, 768]

# Get the similarity scores for the embeddings
similarities = model.similarity(embeddings, embeddings)
print(similarities)
# tensor([[1.0000, 0.9940, 0.1780],
#         [0.9940, 1.0000, 0.1682],
#         [0.1780, 0.1682, 1.0000]])
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

* Size: 14,446 training samples
* Columns: <code>sentence_0</code> and <code>sentence_1</code>
* Approximate statistics based on the first 1000 samples:
  |         | sentence_0                                                                       | sentence_1                                                                        |
  |:--------|:---------------------------------------------------------------------------------|:----------------------------------------------------------------------------------|
  | type    | string                                                                           | string                                                                            |
  | details | <ul><li>min: 3 tokens</li><li>mean: 7.92 tokens</li><li>max: 47 tokens</li></ul> | <ul><li>min: 4 tokens</li><li>mean: 10.32 tokens</li><li>max: 60 tokens</li></ul> |
* Samples:
  | sentence_0                       | sentence_1                    |
  |:---------------------------------|:------------------------------|
  | <code>유튜브 동영상 내용 정리해서 보여줘</code> | <code>이 영상 핵심 정리해줘</code>     |
  | <code>재생 멈춰</code>               | <code>재생 중지 및 큐 초기화</code>    |
  | <code>블로그 인웹사이트 v2로 분석해줘</code>  | <code>블로그 인사이트 v2로 분석해</code> |
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
| 0.2769 | 500  | 0.4662        |
| 0.5537 | 1000 | 0.2116        |
| 0.8306 | 1500 | 0.1512        |
| 0.2769 | 500  | 0.1445        |
| 0.5537 | 1000 | 0.1215        |
| 0.8306 | 1500 | 0.0910        |
| 0.2769 | 500  | 0.0581        |
| 0.5537 | 1000 | 0.0483        |
| 0.8306 | 1500 | 0.0402        |
| 0.2769 | 500  | 0.0281        |
| 0.5537 | 1000 | 0.0273        |
| 0.8306 | 1500 | 0.0213        |
| 0.2769 | 500  | 0.0147        |
| 0.5537 | 1000 | 0.0129        |
| 0.8306 | 1500 | 0.0139        |


### Framework Versions
- Python: 3.14.3
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