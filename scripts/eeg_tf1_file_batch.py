import json
import logging
import sys
import traceback
from datetime import datetime

import pandas as pd

import tensorflow as tf

import settings
from data_tools.batch_manager import BatchManager
from data_tools.data_saver import DataSaver
from utils.logging_utils import logging_reconfig


def weight_variable(shape):
    initial = tf.truncated_normal(shape, stddev=0.1)
    return tf.Variable(initial)


def bias_variable(shape):
    initial = tf.constant(0.1, shape=shape)
    return tf.Variable(initial)


def conv2d(x, W):
    return tf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='SAME')


def max_pool_2x2(x):
    return tf.nn.max_pool(x, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')


logging_reconfig()


def main(db_uid=None):
    bm = BatchManager().load(db_uid)
    # The input x will consist of a tensor of floating point numbers of shape (?, 124, 32, 3)
    x = tf.placeholder(tf.float32, shape=[None, bm.n_channels, bm.trial_size, bm.n_comps])
    # The target output classes y_ will consist of a 2d tensor, where each row is a one-hot 6-dimensional vector
    # indicating which digit class (zero through 5) the corresponding trial belongs to
    y_ = tf.placeholder(tf.float32, shape=[None, bm.n_classes])

    result = dict()

    # First Convolutional Layer.
    # It will compute 32 features for each 5x5 patch. Its weight tensor will have a shape of
    # [5, 5, 3, 32]. The first two dimensions are the patch size, the next is the number of electric field components,
    # and the last is the number of output components
    result.update({'W_conv1': [5, 5, 3, 32]})
    W_conv1 = weight_variable([5, 5, 3, 32])
    logging.info("First convolutional layer: [5, 5, 3, 32]")
    # a bias vector with a component for each output channel
    b_conv1 = bias_variable([32])
    # Apply the layer by convolving x with the weight tensor, add the bias, and apply the ReLU function
    h_conv1 = tf.nn.relu(conv2d(x, W_conv1) + b_conv1)
    # Finally max pool with a 2x2 patch. The result has shape (?, 62, 8, 32)
    h_pool1 = max_pool_2x2(h_conv1)

    # Second Convolutional Layer.
    # Stacks a second layer that provides 64 features for each 5x5 patch
    result.update({'W_conv2': [5, 5, 32, 64]})
    W_conv2 = weight_variable([5, 5, 32, 64])
    b_conv2 = bias_variable([64])
    logging.info("Second convolutional layer: [5, 5, 32, 64]")

    # h_conv2 has dimension (?, 62, 16, 64)
    h_conv2 = tf.nn.relu(conv2d(h_pool1, W_conv2) + b_conv2)
    # h_pool2 has dimension (?, 31, 8, 64)
    h_pool2 = max_pool_2x2(h_conv2)

    # Densely Connected Layer. The image size has been reduced to 31x4. A fully-connected layer with 1024 neurons is
    # added to allow processing on the entire image. The tensor from the pooling layer is reshaped into a batch of
    # vectors, multiplied by a weight matrix, added to a bias, and applied to a ReLU
    result.update({'W_fc1': [31 * 8 * 64, 1024]})
    W_fc1 = weight_variable([31 * 8 * 64, 1024])
    logging.info("First densely-condensed layer: [31 * 8 * 64, 1024]")
    b_fc1 = bias_variable([1024])

    h_pool2_flat = tf.reshape(h_pool2, [-1, 31 * 8 * 64])
    h_fc1 = tf.nn.relu(tf.matmul(h_pool2_flat, W_fc1) + b_fc1)

    # Dropout. TRo reduce overfitting, we will apply dropout before the readout layer. We create a placeholder for the
    # probability that a neuron's output is kept during dropout. This allows us to turn dropout on during training, and
    # turn it off during testing. TensorFlow's tf.nn.dropout op automatically handles scaling neuron outputs in addition
    # to masking them, so dropout just works without any additional scaling.
    keep_prob = tf.placeholder(tf.float32)
    h_fc1_drop = tf.nn.dropout(h_fc1, keep_prob)

    # Readout Layer
    # Finally, we add a layer, just like for the one layer softmax regression above.
    result.update({'W_fc2': [1024, 6]})
    logging.info("Readout layer: [1024, 6]")
    W_fc2 = weight_variable([1024, bm.n_classes])
    b_fc2 = bias_variable([bm.n_classes])

    # implements the convolutional model
    y_conv = tf.matmul(h_fc1_drop, W_fc2) + b_fc2

    # the loss function is the cross-entropy between the target and the softmax activation function applied to the
    # model's prediction. The function tf.nn.softmax_cross_entropy_with_logits internally applies the softmax on the
    # model's unnormalized model prediction and sums across all classes, and tf.reduce_mean takes the average over
    # these sums.
    cross_entropy = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(y_conv, y_))

    # uses steepest gradient descent, with a step length of 0.5, to descend the cross entropy.
    result.update({'AdamOptimizer': 1e-3})
    train_step = tf.train.AdamOptimizer(1e-3).minimize(cross_entropy)

    correct_prediction = tf.equal(tf.argmax(y_conv, 1), tf.argmax(y_, 1))
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

    sess = tf.Session()
    sess.run(tf.initialize_all_variables())

    result.update({'batch_size': bm.batch_size})
    saver = tf.train.Saver()
    train_accuracy = []
    with sess.as_default():
        logging.info("Training the network with a maximum of %s batches of size %s", bm.n_train_batches, bm.batch_size)
        last_iter = 0
        while bm.next_batch():
            acc = accuracy.eval(feed_dict={x: bm.samples('train'), y_: bm.labels('train'), keep_prob: 1.0})
            logging.info("%s: last iter %d - training accuracy: %g", datetime.now().isoformat(), last_iter, acc)
            train_step.run(feed_dict={x: bm.samples('train'), y_: bm.labels('train'), keep_prob: 0.5})
            last_iter += bm.batch_size
            train_accuracy.append({'last_iter': last_iter, 'acc': float(acc)})
        result.update({'train_accuracy': pd.DataFrame(train_accuracy).to_json()})
        try:
            save_path = saver.save(sess, "model_%s.ckpt" % db_uid)
            logging.info("Successfully saved the model in file %s", save_path)
            result.update({'model_file': save_path})
        except Exception as e:
            logging.error("Failed to save the model: %s\n%s", e, traceback.format_exc())
        logging.info("Computing model accuracy")
        test_accuracy = []
        while bm.next_test():
            acc = accuracy.eval(feed_dict={x: bm.samples('test'), y_: bm.labels('test'), keep_prob: 1.0})
            test_accuracy.append(float(acc))
            logging.info("test batch %s of %s: %g", len(test_accuracy) + 1, bm.n_test_batches, acc)
        result.update({'test_accuracy': json.dumps(test_accuracy)})
        logging.info("%s: test accuracy %s", datetime.now().isoformat(), ["%g" % x for x in test_accuracy])
    return result


if __name__ == '__main__':
    logging.info("Using Deep Learning for Brainwave Classification")
    data_saver = DataSaver()
    # db_id = "09e34d85d68f225259083f3e25c679e8"
    # db_id = "684ab9e36c83ffbfd54e26eef6502d97"
    # db_id = "a07a5c40d321cd0a65d91be46974cfdf"
    # db_id = "c446ab9ccefa1b7541312c835c428e3e"
    # db_id = "11f815a091ce5c9d8b3616850ae9bba1"
    db_uid = '9a9d89058dbaa16687ede93d38a051e8'
    doc = main(db_uid=db_uid)
    try:
        doc_id = data_saver.save(settings.MONGO_DNN_COLLECTION, doc=doc)
    except Exception, e:
        logging.error("FAILED TO SAVE RESULT IN THE DATABASE:\n%s\n%s", e, traceback.format_exc())
        sys.exit(1)
    logging.info("Successfully saved the result in the DB: doc #%s", doc_id)
    logging.info("Complete.")
