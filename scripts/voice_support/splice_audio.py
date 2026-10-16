"""Local, non-destructive, pause-boundary audio splicing.

Importing this module does nothing. The caller must first verify the semantic
boundary and actual silence in each source. Energy checks cannot prove that a
word or phoneme is absent. No model, network, rate change or added silence.
"""
import os
os.environ['ORT_DISABLE_TELEMETRY']='1'
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import soundfile as sf


def _rms_dbfs(a):
    rms=float(np.sqrt(np.mean(np.square(a,dtype=np.float64)))) if len(a) else 0.0
    return 20.0*np.log10(max(rms,1e-12))


def splice_arrays(prefix, prefix_rate, prefix_cut, suffix, suffix_rate,
                  suffix_cut, fade_seconds=0.002, max_join_rms_dbfs=-40.0):
    """Return a new mono array and a JSON-safe provenance dictionary.

    Cuts are source-local seconds: keep prefix[:prefix_cut], then
    suffix[suffix_cut:]. Both cuts must be verified silence midpoints. A short
    fade within those quiet regions removes a sample discontinuity without
    inserting silence or overlapping/time-stretching the sources.
    """
    prefix=np.asarray(prefix,dtype=np.float32)
    suffix=np.asarray(suffix,dtype=np.float32)
    if prefix.ndim!=1 or suffix.ndim!=1:
        raise ValueError('Only mono input is supported')
    if not np.isfinite(prefix).all() or not np.isfinite(suffix).all():
        raise ValueError('Input contains non-finite samples')
    if any(isinstance(rate, bool) or not isinstance(rate, (int, np.integer)) for rate in (prefix_rate, suffix_rate)) or prefix_rate!=suffix_rate or prefix_rate<=0:
        raise ValueError('Sample rates must match; resampling is not implicit')
    rate=int(prefix_rate)
    if not np.isfinite([prefix_cut,suffix_cut,fade_seconds]).all():
        raise ValueError('Cut points and fade duration must be finite')
    if not 0<prefix_cut<len(prefix)/rate or not 0<suffix_cut<len(suffix)/rate:
        raise ValueError('Cut points must lie strictly inside their sources')
    if not 0<=fade_seconds<=0.010:
        raise ValueError('Fade must be between zero and 10 milliseconds')
    p=round(prefix_cut*rate);s=round(suffix_cut*rate)
    if not 0<p<len(prefix) or not 0<s<len(suffix):
        raise ValueError('Rounded cut points are outside source samples')
    left=prefix[:p].copy();right=suffix[s:].copy()
    window=max(1,round(0.020*rate))
    left_db=float(_rms_dbfs(left[-window:]));right_db=float(_rms_dbfs(right[:window]))
    if max_join_rms_dbfs is not None and (not np.isfinite(max_join_rms_dbfs) or max_join_rms_dbfs > 0):
        raise ValueError('Join threshold must be finite and at most 0 dBFS')
    if max_join_rms_dbfs is not None and max(left_db,right_db)>max_join_rms_dbfs:
        raise ValueError('A join is not quiet enough; recheck silence and semantic boundaries')
    fade=round(fade_seconds*rate)
    if fade>min(len(left),len(right)):
        raise ValueError('Fade is longer than an output segment')
    if fade==1:
        left[-1]=0;right[0]=0
    elif fade>1:
        left[-fade:]*=np.linspace(1,0,fade,dtype=np.float32)
        right[:fade]*=np.linspace(0,1,fade,dtype=np.float32)
    result=np.concatenate([left,right])
    metadata={
        'composite':True,
        'method':'silence_midpoint_concatenation_with_short_boundary_fades',
        'sample_rate':rate,
        'output_samples':len(result),
        'output_duration_seconds':len(result)/rate,
        'prefix_cut_sample':p,'prefix_cut_seconds':p/rate,
        'suffix_cut_sample':s,'suffix_cut_seconds':s/rate,
        'splice_output_sample':p,'splice_output_seconds':p/rate,
        'fade_each_side_samples':fade,'fade_each_side_seconds':fade/rate,
        'left_join_20ms_rms_dbfs':left_db,'right_join_20ms_rms_dbfs':right_db,
        'join_sample_jump':float(abs(result[p]-result[p-1])),
        'inserted_silence_samples':0,'time_stretched':False,
        'semantic_boundary_verified_by_this_function':False,
    }
    return result,metadata


def write_composite(prefix_path,suffix_path,prefix_cut,suffix_cut,output_path,
                    report_path=None,fade_seconds=0.002,max_join_rms_dbfs=-40.0):
    """Write a new PCM-24 WAV and provenance JSON; never overwrite sources."""
    prefix_path=Path(prefix_path);suffix_path=Path(suffix_path);output_path=Path(output_path)
    report_path=Path(report_path) if report_path else output_path.with_suffix('.json')
    paths=[prefix_path.resolve(),suffix_path.resolve()]
    if output_path.resolve() in paths or report_path.resolve() in paths:
        raise ValueError('Output/report must not replace an input')
    if output_path.resolve()==report_path.resolve():
        raise ValueError('Output and report must be different files')
    if output_path.exists() or report_path.exists():
        raise FileExistsError('Output or report already exists; choose new paths')
    prefix,pr=sf.read(prefix_path,dtype='float32');suffix,sr=sf.read(suffix_path,dtype='float32')
    result,metadata=splice_arrays(prefix,pr,prefix_cut,suffix,sr,suffix_cut,
                                 fade_seconds,max_join_rms_dbfs)
    if np.max(np.abs(result),initial=0)>=1:
        raise ValueError('Output would clip in PCM encoding')
    metadata['sources']=[
        {'role':'prefix','path':str(prefix_path),'sha256':hashlib.sha256(prefix_path.read_bytes()).hexdigest()},
        {'role':'suffix','path':str(suffix_path),'sha256':hashlib.sha256(suffix_path.read_bytes()).hexdigest()},
    ]
    # Exclusive creation avoids silently replacing any file after validation.
    with output_path.open('xb') as file:
        sf.write(file,result,pr,format='WAV',subtype='PCM_24')
    metadata['output_sha256']=hashlib.sha256(output_path.read_bytes()).hexdigest()
    with report_path.open('x') as file:
        json.dump(metadata,file,ensure_ascii=False,indent=2)
    return metadata


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix',type=Path,required=True)
    parser.add_argument('--suffix',type=Path,required=True)
    parser.add_argument('--prefix-cut',type=float,required=True)
    parser.add_argument('--suffix-cut',type=float,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--fade-ms',type=float,default=2.0)
    parser.add_argument('--max-join-rms-dbfs',type=float,default=-40.0)
    args=parser.parse_args()
    metadata=write_composite(args.prefix,args.suffix,args.prefix_cut,args.suffix_cut,
                             args.output,args.report,args.fade_ms/1000,args.max_join_rms_dbfs)
    print(json.dumps(metadata,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
