from __future__ import print_function
'''
http://www.mdsplus.org/index.php?title=Documentation:Tutorial:RemoteAccess&open=76203664636339686324830207&page=Documentation%2FThe+MDSplus+tutorial%2FRemote+data+access+in+MDSplus
http://piscope.psfc.mit.edu/index.php/MDSplus_%26_python#Simple_example_of_reading_MDSplus_data
http://www.mdsplus.org/documentation/beginners/expressions.shtml
http://www.mdsplus.org/index.php?title=Documentation:Tutorial:MdsObjects&open=76203664636339686324830207&page=Documentation%2FThe+MDSplus+tutorial%2FThe+Object+Oriented+interface+of+MDSPlus
'''

'''TODO
- mapping to flux surfaces: its not always [0,1]!
- handling of 1D signals during preprocessing & normalization
- handling of 1D signals for feeding into RNN (convolutional layers)
- handling of missing data in shots?
- TEST
'''
try:
	from MDSplus import *
except ImportError:
	pass
#from pylab import *
import numpy as np
import sys
import multiprocessing as mp
from functools import partial
import Queue
import os
import errno

# import gadata

# from plasma.primitives.shots import ShotList

#from signals import *

#print("Importing numpy version"+np.__version__)

def create_missing_value_filler():
	time = np.linspace(0,100,100)
	vals = np.zeros_like(time)
	return time,vals

def mkdirdepth(filename):
	folder=os.path.dirname(filename)
	if not os.path.exists(folder):
		os.makedirs(folder)

def format_save_path(prepath,signal_path,shot_num):
	return prepath + signal_path  + '/{}.txt'.format(shot_num)


def save_shot(shot_num_queue,c,signals,save_prepath,machine,sentinel=-1):
	missing_values = 0
	# if machine == 'd3d':
	# 	reload(gadata) #reloads Gadata object with connection
	while True:
		shot_num = shot_num_queue.get()
		if shot_num == sentinel:
			break
		shot_complete = True
		for signal in signals:
			signal_path = signal.get_path(machine)
			save_path_full = signal.get_file_path(save_prepath,machine,shot_num)
			success = False
			mapping = None
			if os.path.isfile(save_path_full):
				print('-',end='')
				success = True
			else:
				try:
					try:
						time,data,mapping,success = machine.fetch_data(signal,shot_num,c) 
					except:
						#missing_values += 1
						print('Signal {}, shot {} missing. Filling with zeros'.format(signal_path,shot_num))
						time,data = create_missing_value_filler()
						mapping = None

					
					data_two_column = np.vstack((np.atleast_2d(time),np.atleast_2d(data))).transpose()
					if mapping is not None:
						mapping_two_column = np.hstack((np.array([[0.0]]),np.atleast_2d(mapping)))
						data_two_column = np.vstack((mapping_two_column,data_two_column))
					try: #can lead to race condition
						mkdirdepth(save_path_full)
					except OSError, e:
					    if e.errno == errno.EEXIST:
					        # File exists, and it's a directory, another process beat us to creating this dir, that's OK.
					        pass
					    else:
					        # Our target dir exists as a file, or different error, reraise the error!
					        raise
					np.savetxt(save_path_full,data_two_column,fmt = '%.5e')#fmt = '%f %f')
					print('.',end='')
				except:
					print('Could not save shot {}, signal {}'.format(shot_num,signal_path))
					print('Warning: Incomplete!!!')
					raise
			sys.stdout.flush()
			if not success:
				missing_values += 1
				shot_complete = False
		#only add shot to list if it was complete
		if shot_complete:
			print('saved shot {}'.format(shot_num))
			#complete_queue.put(shot_num)
		else:
			print('shot {} not complete. removing from list.'.format(shot_num))
	print('Finished with {} missing values total'.format(missing_values))
	return


def download_shot_numbers(shot_numbers,save_prepath,machine,signals):
	max_cores = machine.max_cores
	sentinel = -1
	fn = partial(save_shot,signals=signals,save_prepath=save_prepath,machine=machine,sentinel=sentinel)
	num_cores = min(mp.cpu_count(),max_cores) #can only handle 8 connections at once :(
	queue = mp.Queue()
	#complete_shots = Array('i',zeros(len(shot_numbers)))# = mp.Queue()
	
	assert(len(shot_numbers) < 32000) # mp.queue can't handle larger queues yet!
	for shot_num in shot_numbers:
		queue.put(shot_num)
	for i in range(num_cores):
		queue.put(sentinel)
	connections = [Connection(machine.server) for _ in range(num_cores)]
	processes = [mp.Process(target=fn,args=(queue,connections[i])) for i in range(num_cores)]
	
	print('running in parallel on {} processes'.format(num_cores))
	
	for p in processes:
		p.start()
	for p in processes:
		p.join()


def download_all_shot_numbers(prepath,save_path,shot_list_files,signals_full):
	max_len = 30000

	machine = shot_list_files.machine
	signals = []
	for sig in signals_full:
		if not sig.is_defined_on_machine(machine):
			print('Signal {} not defined on machine {}, omitting'.format(sig,machine))
		else:
			signals.append(sig)
	save_prepath = prepath+save_path + '/' 
	shot_numbers,_ = shot_list_files.get_shot_numbers_and_disruption_times()
	shot_numbers_chunks = [shot_numbers[i:i+max_len] for i in xrange(0,len(shot_numbers),max_len)]#can only use queue of max size 30000
	start_time = time.time()
	for shot_numbers_chunk in shot_numbers_chunks:
		download_shot_numbers(shot_numbers_chunk,save_prepath,machine,signals)
	
	print('Finished downloading {} shots in {} seconds'.format(len(shot_numbers),time.time()-start_time))

