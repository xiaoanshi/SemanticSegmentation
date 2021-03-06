import tensorflow as tf
from tensorflow.contrib.framework.python.ops.variables import get_or_create_global_step
from tensorflow.python.platform import tf_logging as logging
from enet import ENet, ENet_arg_scope, ENet_Small
from erfnet import ErfNet, ErfNet_Small
from preprocessing import preprocess
import os
import time
import numpy as np
import matplotlib.pyplot as plt
slim = tf.contrib.slim

#============INPUT ARGUMENTS================
flags = tf.app.flags

#Directories
flags.DEFINE_string('dataset_dir', './dataset', 'The dataset base directory.')
flags.DEFINE_string('dataset_name', 'RSSCarla2c', 'The dataset subdirectory to find the test images.')
flags.DEFINE_string('checkpoint_dir', './log/train_RSSCityscapes2c_ErfNet_Small_ENET_lr_0.001_bs_10', 'The checkpoint directory to restore your model')
flags.DEFINE_string('logdir', './log/test', 'The log directory for event files created during test evaluation.')
flags.DEFINE_boolean('combine_val', False, 'If True, combines the validation with the test dataset.')
flags.DEFINE_boolean('combine_train', False, 'If True, combines the train with the test dataset.')

#Evaluation information
flags.DEFINE_string('network', 'ErfNet', 'The type of network to use.') 
flags.DEFINE_integer('num_classes', 2, 'The number of classes to predict.') #12
flags.DEFINE_integer('batch_size', 1, 'The batch_size for evaluation.') #10
flags.DEFINE_integer('image_height', 88, "The input height of the images.") #360
flags.DEFINE_integer('image_width', 200, "The input width of the images.") #480
flags.DEFINE_integer('num_epochs', 1, "The number of epochs to evaluate your model.") #10

#Architectural changes
flags.DEFINE_integer('num_initial_blocks', 1, 'The number of initial blocks to use in ENet.')
flags.DEFINE_integer('stage_two_repeat', 1, 'The number of times to repeat stage two.')
flags.DEFINE_boolean('skip_connections', False, 'If True, perform skip connections from encoder to decoder.')

FLAGS = flags.FLAGS

#==========NAME HANDLING FOR CONVENIENCE==============
network = FLAGS.network
num_classes = FLAGS.num_classes
batch_size = FLAGS.batch_size
image_height = FLAGS.image_height
image_width = FLAGS.image_width
num_epochs = FLAGS.num_epochs
combine_val = FLAGS.combine_val
combine_train = FLAGS.combine_train

#Architectural changes
num_initial_blocks = FLAGS.num_initial_blocks
stage_two_repeat = FLAGS.stage_two_repeat
skip_connections = FLAGS.skip_connections

dataset_dir = FLAGS.dataset_dir
dataset_name = FLAGS.dataset_name
checkpoint_dir = FLAGS.checkpoint_dir

logdir = FLAGS.logdir

is_training = False

#===============PREPARATION FOR TRAINING==================
#Checkpoint directories
checkpoint_file = tf.train.latest_checkpoint(checkpoint_dir)

#Dataset directories
image_files = sorted([os.path.join(dataset_dir, dataset_name, 'test', file) for file in os.listdir(os.path.join(dataset_dir, dataset_name, 'test')) if file.endswith('.png')])
annotation_files = sorted([os.path.join(dataset_dir, dataset_name, "testannot", file) for file in os.listdir(os.path.join(dataset_dir, dataset_name, "testannot")) if file.endswith('.png')])

image_val_files = sorted([os.path.join(dataset_dir, dataset_name, 'val', file) for file in os.listdir(os.path.join(dataset_dir, dataset_name, 'val')) if file.endswith('.png')])
annotation_val_files = sorted([os.path.join(dataset_dir, dataset_name, 'valannot', file) for file in os.listdir(os.path.join(dataset_dir, dataset_name, 'valannot')) if file.endswith('.png')])

image_train_files = sorted([os.path.join(dataset_dir, dataset_name, 'train', file) for file in os.listdir(os.path.join(dataset_dir, dataset_name, 'train')) if file.endswith('.png')])
annotation_train_files = sorted([os.path.join(dataset_dir, dataset_name, 'trainannot', file) for file in os.listdir(os.path.join(dataset_dir, dataset_name, 'trainannot')) if file.endswith('.png')])


if combine_val:
    image_files += image_val_files
    annotation_files += annotation_val_files
if combine_train:
    image_files += image_train_files
    annotation_files += annotation_train_files

num_batches_per_epoch = len(image_files) / batch_size
num_steps_per_epoch = num_batches_per_epoch


#=============EVALUATION=================
def run():
    with tf.Graph().as_default() as graph:
        tf.logging.set_verbosity(tf.logging.INFO)

        #===================TEST BRANCH=======================
        #Load the files into one input queue
        images = tf.convert_to_tensor(image_files)
        annotations = tf.convert_to_tensor(annotation_files)
        input_queue = tf.train.slice_input_producer([images, annotations])

        #Decode the image and annotation raw content
        image = tf.read_file(input_queue[0])
        image = tf.image.decode_image(image, channels=3)
        annotation = tf.read_file(input_queue[1])
        annotation = tf.image.decode_image(annotation)

        #preprocess and batch up the image and annotation
        preprocessed_image, preprocessed_annotation = preprocess(image, annotation, image_height, image_width)
        images, annotations = tf.train.batch([preprocessed_image, preprocessed_annotation], batch_size=batch_size, allow_smaller_final_batch=True)

        #Create the model inference
        with slim.arg_scope(ENet_arg_scope()):
	    if (network == 'ENet'):
		print ('Building the network: ' , network)
                logits, probabilities = ENet(images,
                                         num_classes,
                                         batch_size=batch_size,
                                         is_training=is_training,
                                         reuse=None,
                                         num_initial_blocks=num_initial_blocks,
                                         stage_two_repeat=stage_two_repeat,
                                         skip_connections=skip_connections)

	    if (network == 'ENet_Small'):
		print ('Building the network: ' , network)
                logits, probabilities = ENet_Small(images,
                                         num_classes,
                                         batch_size=batch_size,
                                         is_training=is_training,
                                         reuse=None,
                                         num_initial_blocks=num_initial_blocks,
                                         skip_connections=skip_connections)

	    if (network == 'ErfNet'):
		print ('Building the network: ' , network)
                logits, probabilities = ErfNet(images,
                                         num_classes,
                                         batch_size=batch_size,
                                         is_training=is_training,
                                         reuse=None)

	    if (network == 'ErfNet_Small'):
		print ('Building the network: ' , network)
                logits, probabilities = ErfNet_Small(images,
                                         num_classes,
                                         batch_size=batch_size,
                                         is_training=is_training,
                                         reuse=None)

        # Set up the variables to restore and restoring function from a saver.
        exclude = []
        variables_to_restore = slim.get_variables_to_restore(exclude=exclude)

        saver = tf.train.Saver(variables_to_restore)
        def restore_fn(sess):
            return saver.restore(sess, checkpoint_file)

        #perform one-hot-encoding on the ground truth annotation to get same shape as the logits
        annotations = tf.reshape(annotations, shape=[batch_size, image_height, image_width])
        annotations_ohe = tf.one_hot(annotations, num_classes, axis=-1)
        annotations = tf.cast(annotations, tf.int64)

        #State the metrics that you want to predict. We get a predictions that is not one_hot_encoded.
        predictions = tf.argmax(probabilities, -1)
        accuracy, accuracy_update = tf.contrib.metrics.streaming_accuracy(predictions, annotations)
        mean_IOU, mean_IOU_update = tf.contrib.metrics.streaming_mean_iou(predictions=predictions, labels=annotations, num_classes=num_classes)
        per_class_accuracy, per_class_accuracy_update = tf.metrics.mean_per_class_accuracy(labels=annotations, predictions=predictions, num_classes=num_classes)
        metrics_op = tf.group(accuracy_update, mean_IOU_update, per_class_accuracy_update)

        #Create the global step and an increment op for monitoring
        global_step = get_or_create_global_step()
        global_step_op = tf.assign(global_step, global_step + 1) #no apply_gradient method so manually increasing the global_step

        #Create a evaluation step function
        def eval_step(sess, metrics_op, global_step):
            '''
            Simply takes in a session, runs the metrics op and some logging information.
            '''
            _, global_step_count, accuracy_value, mean_IOU_value, per_class_accuracy_value = sess.run([metrics_op, global_step_op, accuracy, mean_IOU, per_class_accuracy])

            #Log some information
            logging.info('Global Step %s: Streaming Accuracy: %.4f     Streaming Mean IOU: %.4f     Per-class Accuracy: %.4f (%.2f sec/step)',
                         global_step_count, accuracy_value, mean_IOU_value, per_class_accuracy_value)

            return accuracy_value, mean_IOU_value, per_class_accuracy_value

       
        #Define your supervisor for running a managed session. Do not run the summary_op automatically or else it will consume too much memory
        sv = tf.train.Supervisor(logdir = logdir, summary_op = None, init_fn=restore_fn)

        #Run the managed session
        with sv.managed_session() as sess:
            start_time = time.time()
            for step in range(int(num_steps_per_epoch * num_epochs)):
		_, global_step_count, test_accuracy, test_mean_IOU, test_per_class_accuracy = sess.run([metrics_op, global_step_op, accuracy, mean_IOU, per_class_accuracy])

            time_elapsed = time.time() - start_time

            #At the end of all the evaluation, show the final accuracy
            logging.info('Final Streaming Accuracy: %.4f', test_accuracy)
            logging.info('Final Mean IOU: %.4f', test_mean_IOU)
            logging.info('Final Per Class Accuracy %.4f', test_per_class_accuracy)
            logging.info('Time Elapsed %.4f', time_elapsed)
            logging.info('FPS %.4f', (num_steps_per_epoch * num_epochs)/time_elapsed)

            #Show end of evaluation
            logging.info('Finished evaluating!')


if __name__ == '__main__':
    run()
