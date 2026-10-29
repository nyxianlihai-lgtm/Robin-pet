"""Defringe a keyed character's external silhouette, preserving opaque details."""
import cv2
import numpy as np


def clean_character_edge(image):
    alpha=image[:,:,3]
    count,labels,stats,_=cv2.connectedComponentsWithStats(np.uint8(alpha>=128))
    if count<2:
        return image.copy(),np.zeros(alpha.shape,bool)
    largest=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
    body=np.uint8(labels==largest)
    contours,_=cv2.findContours(body,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    filled=np.zeros_like(body)
    cv2.drawContours(filled,contours,-1,1,cv2.FILLED)
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
    inner=cv2.erode(filled,kernel)
    solid=(inner>0)&(alpha>=250)
    if not np.any(solid):
        return image.copy(),np.zeros(alpha.shape,bool)
    distance,nearest=cv2.distanceTransformWithLabels(np.uint8(~solid),cv2.DIST_L2,5,labelType=cv2.DIST_LABEL_PIXEL)
    palette=np.zeros((int(nearest.max())+1,3),np.uint8)
    palette[nearest[solid]]=image[:,:,:3][solid]
    inward=palette[nearest].astype(np.float32)
    exterior_ring=(cv2.dilate(filled,np.ones((3,3),np.uint8))>0)&(inner==0)&(alpha>0)
    color=image[:,:,:3].astype(np.float32)
    a=alpha.astype(np.float32)/255
    neutral=(np.max(color,axis=2)-np.min(color,axis=2)<35)&(np.max(color,axis=2)>100)
    # Preserve the drawn dark outline; replace gray screen contamination with
    # nearby opaque foreground color. Interior eyes/white details are excluded.
    mix=np.where(a<.98,1.0,np.where(neutral,.65,0)).astype(np.float32)
    mix*=exterior_ring
    mix*=distance<=3.5  # Do not borrow distant colors for thin gold ornaments.
    result=image.copy()
    result[:,:,:3]=np.uint8(np.clip(color*(1-mix[:,:,None])+inward*mix[:,:,None],0,255).round())
    eroded=cv2.erode(alpha,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    soften=exterior_ring&(alpha<250)
    result[:,:,3][soften]=np.uint8((alpha[soften]*.35+eroded[soften]*.65).round())
    result[:,:,:3][(result[:,:,3]==0)&exterior_ring]=0
    return result,exterior_ring
