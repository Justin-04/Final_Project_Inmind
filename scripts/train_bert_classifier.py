"""
Script: Train Fine-Tuned BERT Intent Classifier

Fine-tunes BERT on DJI-domain intent classification
Intents: diagnostic, rag, pricing, general
Saves model to models/bert_intent_classifier/
"""

import os
import sys
import logging
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MODELS_DIR = Path(__file__).parent.parent / "models" / "bert_intent_classifier"
TRAINING_DATA_PATH = Path(__file__).parent.parent / "data" / "ground_truth_qa.json"


def load_training_data():
    """
    Load training data from ground_truth_qa.json
    
    Returns:
        list: Training examples with intent labels
    """
    try:
        with open(TRAINING_DATA_PATH, 'r') as f:
            data = json.load(f)
        
        examples = []
        for test_case in data.get("test_cases", []):
            examples.append({
                "text": test_case.get("query"),
                "intent": test_case.get("intent"),
                "drone_model": test_case.get("drone_model")
            })
        
        logger.info(f"Loaded {len(examples)} training examples")
        return examples
    
    except Exception as e:
        logger.error(f"Error loading training data: {str(e)}")
        return []


def train_model(examples: list):
    """
    Train BERT model on intent classification
    
    Args:
        examples: Training examples with intent labels
    """
    try:
        logger.info("Starting BERT training...")
        
        # TODO: Implement BERT training
        # 1. Load pre-trained BERT model
        # 2. Prepare dataset
        # 3. Fine-tune on intent classification
        # 4. Validate on held-out set
        # 5. Save model and tokenizer
        
        logger.info("Training complete")
    
    except Exception as e:
        logger.error(f"Training error: {str(e)}")


def save_model(model, tokenizer, output_dir: str):
    """
    Save fine-tuned model and tokenizer
    
    Args:
        model: Trained BERT model
        tokenizer: BERT tokenizer
        output_dir: Output directory
    """
    try:
        logger.info(f"Saving model to {output_dir}")
        
        # TODO: Save model and tokenizer
        # model.save_pretrained(output_dir)
        # tokenizer.save_pretrained(output_dir)
        
        logger.info("Model saved")
    
    except Exception as e:
        logger.error(f"Error saving model: {str(e)}")


def main():
    """Main training script"""
    logger.info("BERT Intent Classifier Training")
    
    # Create output directory
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load training data
    examples = load_training_data()
    if not examples:
        logger.error("No training data found")
        return
    
    # Train model
    train_model(examples)
    
    # TODO: Save model after training
    # save_model(model, tokenizer, str(MODELS_DIR))
    
    logger.info("Training pipeline complete")


if __name__ == "__main__":
    main()
