
import torch,json
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
import os,sys

from utils import log_method,load_bert,read_json,write_json,ClearCache


def batch_encode_strings(bert, tokenizer, strings, batch_size=16):
    model = bert
    model.eval()  # Set the model to evaluation mode

    # Initialize list to store the vectors
    vectors = []

    # Process strings in batches
    for i in tqdm(range(0, len(strings), batch_size)):
        # Prepare batch data
        batch = strings[i:i + batch_size]
        inputs = tokenizer(batch, padding=True, truncation=True, return_tensors="pt", max_length=512)

        # Move tensors to the device where the model is located
        input_ids = inputs['input_ids'].to("cuda:0")
        attention_mask = inputs['attention_mask'].to("cuda:0")

        # Get hidden states
        with torch.no_grad():
            outputs = model(input_ids, attention_mask=attention_mask)
            hidden_states = outputs.last_hidden_state  # Use the last hidden states
        del inputs, batch
        # Compute mean of all token embeddings for each sentence in the batch
        batch_vectors = hidden_states.mean(dim=1)
        vectors.extend(batch_vectors)
        del batch_vectors

    # Convert the list of tensors to a single tensor
    vectors = torch.stack(vectors).cpu()
    return vectors

def apply_dim_reduction(vectors, n_components=2):
    pca = PCA(n_components)  # Adjust components according to your dataset size and desired variance
    reduced_vectors = pca.fit_transform(vectors)

    return reduced_vectors

def apply_clustering(k, reduced_vectors):
    kmeans = KMeans(n_clusters=k, random_state=42)
    kmeans.fit(reduced_vectors)
    centers = kmeans.cluster_centers_

    return centers

def find_most_centered_data(centers, reduced_vectors):
    closest_data = []
    for center in centers:
        distances = np.linalg.norm(reduced_vectors - center, axis=1)
        closest_data.append(np.argmin(distances))

    return closest_data


def find_center_examples(bert, tokenizer, task_json,k):
    # Your list of strings
    strings = task_json['Full clustering context']
    
    # Use the average of the last hidden states as vector representations
    vectors = batch_encode_strings(bert, tokenizer, strings, batch_size=16)

    # Dimensionality reduction with PCA
    reduced_vectors = apply_dim_reduction(vectors, n_components=2)
    centers = apply_clustering(k, reduced_vectors)

    # Find the closest data points to the cluster centers
    closest_data = find_most_centered_data(centers, reduced_vectors)

    per_task_new_example_list = []
    for each in closest_data:
        
        question = task_json['Instances'][each]['input']
        answer = task_json['Instances'][each]['answer_prediction']
        reason = task_json['Instances'][each]['fb_pred']
        data_dict = {"input":question,"output":answer,"reason":reason}
        per_task_new_example_list.append(data_dict)

    return reduced_vectors, centers, closest_data,per_task_new_example_list

def visualize_clustering(reduced_vectors, centers, closest_data):
    # 'closest_data' now contains the indices of strings that are closest to the cluster centers
    print("Indices of strings closest to cluster centers:", closest_data)
    # Visualization
    fig = plt.figure()
    ax = fig.add_subplot(11)

    # Plot the reduced vectors
    ax.scatter(reduced_vectors[:, 0], reduced_vectors[:, 1], alpha=0.5)

    # Plot the cluster centers
    ax.scatter(centers[:, 0], centers[:, 1], color='r', marker='x', s=100, label='Centers')

    # Mark the closest vectors to the cluster centers
    for index in closest_data:
        ax.scatter(reduced_vectors[index, 0], reduced_vectors[index, 1], 
                color='g', marker='o', s=100, edgecolor='k', label='Closest to Center' if index == closest_data[0] else "")

    ax.set_xlabel('PCA 1')
    ax.set_ylabel('PCA 2')

    ax.set_title('BERT Vectors in 2D space with Cluster Centers')
    ax.legend()

    plt.savefig("1.png")


# visualize_clustering(reduced_vectors, centers, closest_data_indices)
@log_method
def get_new_examples():
    with ClearCache():
        arguments = json.loads(sys.argv[1])
        experiment_root_path = arguments['experiment_root_path']
        fb_dataset_path = arguments['feedback_dataset_path']
        k = arguments['k']
        new_example_dict_path = arguments['prompt_example_dict_path']

        feedback_dataset = read_json(fb_dataset_path)


        bert, tokenizer = load_bert()

        all_new_example_dict = {}

        for key in feedback_dataset.keys():
            if '.json' in key:
                reduced_vectors, centers, closest_data_indices, per_task_new_example_list = find_center_examples(bert, tokenizer, feedback_dataset[key],k)
                #TODO:make sure the path is correct.
                task_result_path = os.path.join(experiment_root_path, "prompt_example_clustering",key.split('.json')[0])
                os.makedirs(task_result_path)
                torch.save(reduced_vectors,os.path.join(task_result_path,"reduced_vectors.pt"))
                torch.save(centers,os.path.join(task_result_path,"centers.pt"))
                torch.save(closest_data_indices,os.path.join(task_result_path,"closest_data_indices.pt"))

                all_new_example_dict[key] = per_task_new_example_list

        write_json(new_example_dict_path, all_new_example_dict)

        del bert, tokenizer, all_new_example_dict,feedback_dataset
    sys.exit()

get_new_examples()