"""
Train a DistilBERT Intent Classifier for DJI Drone queries.

Classes: rag, diagnostic, pricing
Model: distilbert-base-uncased (66M params, fast inference)

Usage:
    pip install transformers datasets torch scikit-learn
    python scripts/train_bert_classifier.py

Saves to: models/bert_intent_classifier/
"""

import json
import os
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

from datasets import Dataset
from transformers import (
    DistilBertTokenizer,
    DistilBertForSequenceClassification,
    TrainingArguments,
    Trainer,
)

# ─── Config ───────────────────────────────────────────────────────────────────

DATA_PATH = Path(__file__).parent.parent / "models" / "bert_intent_classifier" / "intent_training_data.json"
OUTPUT_DIR = Path(__file__).parent.parent / "models" / "bert_intent_classifier" / "model"
MODEL_NAME = "distilbert-base-uncased"

LABEL_MAP = {"rag": 0, "diagnostic": 1, "pricing": 2}
ID_TO_LABEL = {v: k for k, v in LABEL_MAP.items()}
NUM_LABELS = len(LABEL_MAP)

EPOCHS = 10
BATCH_SIZE = 16
LEARNING_RATE = 5e-5
TEST_SPLIT = 0.2


# ─── Load Data ────────────────────────────────────────────────────────────────

def load_data():
    print(f"Loading data from {DATA_PATH}...")
    with open(DATA_PATH, "r") as f:
        data = json.load(f)

    texts = [item["text"] for item in data]
    labels = [LABEL_MAP[item["label"]] for item in data]

    print(f"  Total examples: {len(texts)}")
    for label_name, label_id in LABEL_MAP.items():
        count = labels.count(label_id)
        print(f"    {label_name}: {count}")

    return texts, labels


# ─── Tokenize ─────────────────────────────────────────────────────────────────

def tokenize_data(texts, labels, tokenizer):
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=TEST_SPLIT, random_state=42, stratify=labels
    )

    def tokenize(examples):
        return tokenizer(
            examples["text"],
            padding="max_length",
            truncation=True,
            max_length=128,
        )

    train_dataset = Dataset.from_dict({"text": train_texts, "label": train_labels})
    val_dataset = Dataset.from_dict({"text": val_texts, "label": val_labels})

    train_dataset = train_dataset.map(tokenize, batched=True)
    val_dataset = val_dataset.map(tokenize, batched=True)

    train_dataset.set_format("torch", columns=["input_ids", "attention_mask", "label"])
    val_dataset.set_format("torch", columns=["input_ids", "attention_mask", "label"])

    print(f"  Train: {len(train_dataset)}, Val: {len(val_dataset)}")
    return train_dataset, val_dataset, val_texts, val_labels


# ─── Metrics ──────────────────────────────────────────────────────────────────

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    accuracy = (predictions == labels).mean()
    return {"accuracy": accuracy}


# ─── Train ────────────────────────────────────────────────────────────────────

def train():
    print("=" * 60)
    print("  BERT INTENT CLASSIFIER TRAINING")
    print("=" * 60)
    print(f"  Model: {MODEL_NAME}")
    print(f"  Classes: {list(LABEL_MAP.keys())}")
    print(f"  Epochs: {EPOCHS}, Batch: {BATCH_SIZE}, LR: {LEARNING_RATE}")
    print()

    # Load data
    texts, labels = load_data()

    # Load tokenizer and model
    print(f"\nLoading {MODEL_NAME}...")
    tokenizer = DistilBertTokenizer.from_pretrained(MODEL_NAME)
    model = DistilBertForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=NUM_LABELS,
        id2label=ID_TO_LABEL,
        label2id=LABEL_MAP,
    )

    # Tokenize
    print("\nTokenizing...")
    train_dataset, val_dataset, val_texts, val_labels = tokenize_data(texts, labels, tokenizer)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        logging_steps=10,
        seed=42,
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
    )

    # Train
    print("\nTraining...")
    trainer.train()

    # Evaluate
    print("\n" + "=" * 60)
    print("  EVALUATION")
    print("=" * 60)

    predictions = trainer.predict(val_dataset)
    preds = np.argmax(predictions.predictions, axis=-1)

    print("\nClassification Report:")
    print(classification_report(
        val_labels, preds,
        target_names=list(LABEL_MAP.keys()),
        digits=3,
    ))

    print("Confusion Matrix:")
    print(confusion_matrix(val_labels, preds))

    # Save model
    print(f"\nSaving model to {OUTPUT_DIR}...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    # Save label map
    with open(OUTPUT_DIR / "label_map.json", "w") as f:
        json.dump({"label_map": LABEL_MAP, "id_to_label": ID_TO_LABEL}, f, indent=2)

    print(f"\n{'='*60}")
    print("  TRAINING COMPLETE")
    print(f"  Model saved to: {OUTPUT_DIR}")
    print(f"  Accuracy: {predictions.metrics['test_accuracy']:.2%}")
    print(f"{'='*60}")


if __name__ == "__main__":
    train()
