import os
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

class Retriever:
    def __init__(self, df, dataset):
        self.docs = []
        for i, row in df.iterrows():
            metadata = {'dataset':dataset, 'store_id':row.store_id, 'date':row.date, 'category':row.category, 'record_id':row.transaction_id}
            content = f'Transaction {row.transaction_id} on {row.date}: store {row.store_id}, region {row.region}, category {row.category}, product {row.product_name}, units {row.quantity}, revenue {row.total_sales:.2f}, profit {row.profit:.2f}.'
            self.docs.append({'text':content,'metadata':metadata})
        for category, group in df.groupby('category'):
            self.docs.append({'text':f'Category {category}: revenue {group.total_sales.sum():.2f}, profit {group.profit.sum():.2f}, units {group.quantity.sum()}, across {len(group)} records.', 'metadata':{'dataset':dataset,'category':category,'record_id':'category-summary','store_id':'all','date':'all'}})
        # Chunking preserves source metadata on each chunk.
        self.docs = [dict(text=d['text'][start:start+700],metadata=d['metadata']) for d in self.docs for start in range(0,len(d['text']),600)]
        self.mode = 'TF-IDF local vector retrieval'
        self.model = None
        if not self.docs: return
        model_path = os.getenv('EMBEDDING_MODEL_PATH')
        if model_path:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(model_path, local_files_only=True)
                self.matrix = self.model.encode([d['text'] for d in self.docs], normalize_embeddings=True)
                self.mode = 'Sentence Transformers semantic retrieval'
            except (ImportError, OSError, ValueError):
                self.model = None
        if self.model is None:
            self.vectorizer = TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True)
            self.matrix = self.vectorizer.fit_transform([d['text'] for d in self.docs])

    def search(self, question, limit=5):
        if not self.docs: return []
        if self.model is not None:
            scores = self.matrix @ self.model.encode([question],normalize_embeddings=True)[0]
        else:
            scores = (self.matrix @ self.vectorizer.transform([question]).T).toarray().ravel()
        return [dict(self.docs[i],score=float(scores[i])) for i in np.argsort(scores)[::-1][:limit] if scores[i]>0]
